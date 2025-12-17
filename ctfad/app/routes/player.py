from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, jsonify, request, current_app

from ..models import FlagSubmission, Team, event_has_ended
from ..services import calculate_scores, record_invalid_submission, submit_flag

player_bp = Blueprint("player", __name__, url_prefix="/api")


def authenticate_team() -> Team:
    token = request.headers.get("X-Team-Token")
    team = Team.query.filter_by(api_token=token).one_or_none()
    if team is None:
        from flask import abort

        abort(401, description="Valid team token required")
    return team


@player_bp.route("/teams", methods=["GET"])
def list_teams():
    teams = Team.query.all()
    return jsonify(
        [
            {
                "name": team.name,
                "ip_address": team.ip_address,
            }
            for team in teams
        ]
    )


@player_bp.route("/flags", methods=["POST"])
def submit_flag_route():
    attacker = authenticate_team()
    if event_has_ended():
        return (
            jsonify({"error": "CTF has ended; flag submissions are closed."}),
            403,
        )
    data = request.get_json() or {}
    submitted_flag = data.get("flag")
    if not submitted_flag:
        return jsonify({"error": "Flag required"}), 400

    is_valid, flag = submit_flag(attacker, submitted_flag)
    if not is_valid:
        record_invalid_submission(attacker, submitted_flag)
        return jsonify({"valid": False}), 400

    return jsonify(
        {
            "valid": True,
            "defender": flag.team.name if flag else None,
            "challenge": flag.challenge.name if flag else None,
        }
    )


@player_bp.route("/scoreboard", methods=["GET"])
def public_scoreboard():
    return jsonify(calculate_scores())


@player_bp.route("/attacks", methods=["GET"])
def attack_feed():
    submissions = (
        FlagSubmission.query.order_by(FlagSubmission.created_at.desc()).limit(100).all()
    )
    tz_name = current_app.config.get("TIMEZONE", "UTC")
    try:
        target_tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        target_tz = timezone.utc
    payload = []
    for entry in submissions:
        created_at = entry.created_at
        timestamp = None
        if created_at:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            timestamp = created_at.astimezone(target_tz).isoformat()
        payload.append(
            {
                "time": timestamp,
                "attacker": entry.attacker.name if entry.attacker else None,
                "defender": entry.defender.name if entry.defender else None,
                "challenge": entry.challenge.name if entry.challenge else None,
                "valid": entry.is_valid,
            }
        )
    return jsonify(payload)
