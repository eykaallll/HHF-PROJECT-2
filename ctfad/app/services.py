from __future__ import annotations

import secrets
import socket
import string
import subprocess
from pathlib import Path
from typing import Iterable

from flask import current_app

from .extensions import db
from .models import (
    Challenge,
    Flag,
    FlagAccessToken,
    FlagSubmission,
    SLAResult,
    Team,
    TeamCredential,
    event_has_ended,
)


def generate_flag() -> str:
    config = current_app.config
    alphabet = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(config["FLAG_LENGTH"]))
    return f"{config['FLAG_PREFIX']}{random_part}{config['FLAG_SUFFIX']}"


def generate_team_portal_password(length: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def ensure_team_credentials(team: Team, length: int = 8) -> TeamCredential:
    credential = team.credential
    if credential is not None:
        return credential
    credential = TeamCredential(team=team)
    credential.set_password(generate_team_portal_password(length))
    db.session.add(credential)
    return credential


def ensure_flag_access_token(team: Team, challenge: Challenge) -> FlagAccessToken:
    token = FlagAccessToken.query.filter_by(team=team, challenge=challenge).one_or_none()
    if token is not None:
        return token
    token = FlagAccessToken(team=team, challenge=challenge)
    db.session.add(token)
    return token


def rotate_flags() -> list[Flag]:
    updated_flags: list[Flag] = []
    for team in Team.query.all():
        for challenge in Challenge.query.all():
            flag = Flag.query.filter_by(team=team, challenge=challenge).one_or_none()
            ensure_flag_access_token(team, challenge)
            if flag is None:
                flag = Flag(team=team, challenge=challenge, value=generate_flag())
                db.session.add(flag)
            else:
                flag.value = generate_flag()
            updated_flags.append(flag)
    db.session.commit()
    return updated_flags


def submit_flag(attacker: Team, submitted_flag: str) -> tuple[bool, Flag | None]:
    flag = Flag.query.filter_by(value=submitted_flag).one_or_none()
    if flag is None or flag.team_id == attacker.id:
        return False, flag

    record = FlagSubmission(
        attacker=attacker,
        defender=flag.team,
        challenge=flag.challenge,
        submitted_flag=submitted_flag,
        is_valid=True,
    )
    db.session.add(record)
    db.session.commit()
    return True, flag


def record_invalid_submission(attacker: Team, submitted_flag: str) -> None:
    record = FlagSubmission(
        attacker=attacker,
        defender=None,
        challenge=None,
        submitted_flag=submitted_flag,
        is_valid=False,
    )
    db.session.add(record)
    db.session.commit()


SLA_TIMEOUT_SECONDS = 60


def run_sla_checks(
    tick_number: int,
    teams: Iterable[Team] | None = None,
    challenges: Iterable[Challenge] | None = None,
    pairs: Iterable[tuple[Team, Challenge]] | None = None,
) -> list[SLAResult]:
    if event_has_ended():
        current_app.logger.info("Skipping SLA checks because the event has ended")
        return []
    results: list[SLAResult] = []
    if pairs:
        combos = list(pairs)
    else:
        teams = list(teams or Team.query.all())
        challenges = list(challenges or Challenge.query.all())
        combos = [(team, challenge) for team in teams for challenge in challenges]
    for team, challenge in combos:
        if team is None or challenge is None:
            continue
        passed, details = False, ""
        script_path = Path(challenge.sla_script) if challenge.sla_script else None
        if script_path and script_path.exists():
            result = subprocess.run(
                ["python", str(script_path), team.ip_address, str(challenge.port)],
                capture_output=True,
                text=True,
                timeout=SLA_TIMEOUT_SECONDS,
            )
            passed = result.returncode == 0
            combined_output = "\n".join(
                part for part in (result.stdout, result.stderr) if part
            )
            details = combined_output.strip()
        else:
            if script_path:
                missing_msg = f"SLA script missing at {script_path}"
                current_app.logger.warning(missing_msg)
                details = missing_msg
            default_passed, default_details = _default_sla_probe(team, challenge)
            details = f"{details} | {default_details}" if details else default_details
            passed = default_passed
        sla_result = SLAResult.query.filter_by(
            team_id=team.id,
            challenge_id=challenge.id,
            tick_number=tick_number,
        ).one_or_none()
        if sla_result is None:
            sla_result = SLAResult(
                team=team,
                challenge=challenge,
                tick_number=tick_number,
            )
        sla_result.passed = passed
        sla_result.details = details[:4000] if details else None
        db.session.add(sla_result)
        results.append(sla_result)
    db.session.commit()
    return results


def calculate_scores() -> list[dict[str, int | str]]:
    config = current_app.config
    teams = Team.query.all()
    scoreboard: list[dict[str, int | str]] = []
    for team in teams:
        attack_captures = len([s for s in team.submissions if s.is_valid])
        sla_passes = SLAResult.query.filter_by(team_id=team.id, passed=True).count()
        attack_points = attack_captures * config["FLAG_POINTS"]
        sla_points = sla_passes * config["SLA_POINTS"]
        scoreboard.append(
            {
                "team": team.name,
                "attack_captures": attack_captures,
                "sla_passes": sla_passes,
                "attack_points": attack_points,
                "sla_points": sla_points,
                "total": attack_points + sla_points,
            }
        )
    scoreboard.sort(key=lambda row: row["total"], reverse=True)
    for index, row in enumerate(scoreboard, start=1):
        row["rank"] = index
    return scoreboard


def _default_sla_probe(team: Team, challenge: Challenge, timeout: float = 5.0) -> tuple[bool, str]:
    message = f"TCP probe to {team.ip_address}:{challenge.port}"
    try:
        with socket.create_connection((team.ip_address, challenge.port), timeout=timeout):
            return True, f"{message} succeeded"
    except OSError as exc:
        return False, f"{message} failed ({exc})"


def delete_team(team: Team) -> None:
    """Remove a team and dependent records that are not covered by ORM cascades."""
    # Clear submissions and SLA rows tied to the team to avoid FK constraint errors,
    # especially when using MySQL where attacker_id/defender_id constraints apply.
    db.session.query(FlagSubmission).filter(
        (FlagSubmission.attacker_id == team.id) | (FlagSubmission.defender_id == team.id)
    ).delete(synchronize_session=False)
    db.session.query(SLAResult).filter_by(team_id=team.id).delete(synchronize_session=False)
    db.session.query(Flag).filter_by(team_id=team.id).delete(synchronize_session=False)
    db.session.query(FlagAccessToken).filter_by(team_id=team.id).delete(synchronize_session=False)
    db.session.query(TeamCredential).filter_by(team_id=team.id).delete(synchronize_session=False)
    db.session.delete(team)
    db.session.commit()
