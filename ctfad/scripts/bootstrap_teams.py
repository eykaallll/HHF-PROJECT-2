#!/usr/bin/env python3
"""Create a batch of demo teams with sequential IPs (default: 10.10.0.100-109)."""

from __future__ import annotations

import argparse

from app import create_app
from app.extensions import db
from app.models import Challenge, Team
from app.services import ensure_flag_access_token, ensure_team_credentials

DEFAULT_BASE_PREFIX = "10.10.0."
DEFAULT_START_HOST = 100
DEFAULT_COUNT = 10


def iter_specs(count: int, start_host: int, base_prefix: str):
    for idx in range(count):
        yield f"team{idx + 1:02d}", f"{base_prefix}{start_host + idx}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provision demo teams with predictable IPs for the AD network."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help="Number of teams to create (default: 10)",
    )
    parser.add_argument(
        "--start-host",
        type=int,
        default=DEFAULT_START_HOST,
        help="Starting IPv4 host octet (default: 100)",
    )
    parser.add_argument(
        "--base-prefix",
        default=DEFAULT_BASE_PREFIX,
        help="IPv4 prefix through the third octet (default: 10.10.0.)",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        challenges = list(Challenge.query.all())
        created: list[tuple[Team, str, list[tuple[str, str]]]] = []
        skipped: list[str] = []

        for name, ip_addr in iter_specs(args.count, args.start_host, args.base_prefix):
            existing = Team.query.filter(
                (Team.name == name) | (Team.ip_address == ip_addr)
            ).first()
            if existing:
                skipped.append(name)
                continue
            team = Team(name=name, ip_address=ip_addr)
            db.session.add(team)
            db.session.flush()
            credential = ensure_team_credentials(team)
            tokens: list[tuple[str, str]] = []
            for challenge in challenges:
                token = ensure_flag_access_token(team, challenge)
                tokens.append((challenge.name, token.token))
            created.append((team, credential.password_plain, tokens))

        db.session.commit()

        for team, portal_password, tokens in created:
            print(f"[created] {team.name} @ {team.ip_address}")
            print(f"  api_token: {team.api_token}")
            print(f"  portal_password: {portal_password}")
            for challenge_name, token in tokens:
                print(f"  flag_token[{challenge_name}]: {token}")
        if skipped:
            print(f"[skipped] existing teams: {', '.join(skipped)}")
        if not created:
            print("No new teams created.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
