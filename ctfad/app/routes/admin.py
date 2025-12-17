from __future__ import annotations

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from ..extensions import db
from ..models import Challenge, GameConfig, Team, event_has_ended, get_active_game_config
from ..services import (
    calculate_scores,
    delete_team as delete_team_record,
    ensure_flag_access_token,
    ensure_team_credentials,
    rotate_flags,
    run_sla_checks,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def require_admin() -> None:
    token = request.headers.get("X-Admin-Token")
    if token != current_app.config["ADMIN_TOKEN"]:
        current_app.logger.warning("Unauthorized admin access attempt")
        from flask import abort

        abort(401, description="Admin token required")


@admin_bp.route("/game-config", methods=["GET", "POST"])
def game_config():
    require_admin()
    if request.method == "GET":
        config = get_active_game_config()
        if not config:
            return jsonify({}), 404
        return jsonify(
            {
                "start_time": config.start_time.isoformat(),
                "end_time": config.end_time.isoformat(),
                "tick_length": config.tick_length,
                "num_ticks": config.num_ticks,
            }
        )

    data = request.get_json() or {}
    try:
        start_time_raw = data.get("start_time")
        end_time_raw = data.get("end_time")
        if not start_time_raw or not end_time_raw:
            raise ValueError("start_time and end_time are required")
        start_time = datetime.fromisoformat(start_time_raw)
        end_time = datetime.fromisoformat(end_time_raw)
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid datetime format: {exc}"}), 400

    if start_time >= end_time:
        return jsonify({"error": "start_time must be before end_time"}), 400

    tick_length = int(data.get("tick_length", current_app.config["DEFAULT_TICK_LENGTH"]))
    num_ticks = int(data.get("num_ticks", current_app.config["DEFAULT_NUM_TICKS"]))

    config = GameConfig(
        start_time=start_time,
        end_time=end_time,
        tick_length=tick_length,
        num_ticks=num_ticks,
    )
    db.session.add(config)
    db.session.commit()
    return jsonify({"message": "Configuration saved", "id": config.id})


@admin_bp.route("/teams", methods=["GET", "POST"])
def teams():
    require_admin()
    if request.method == "GET":
        teams = Team.query.all()
        payload: list[dict[str, object]] = []
        for team in teams:
            tokens = [
                {
                    "challenge_id": token.challenge_id,
                    "challenge": token.challenge.name if token.challenge else None,
                    "token": token.token,
                }
                for token in team.flag_access_tokens
            ]
            payload.append(
                {
                    "id": team.id,
                    "name": team.name,
                    "ip_address": team.ip_address,
                    "api_token": team.api_token,
                    "flag_tokens": tokens,
                }
            )
        return jsonify(payload)

    data = request.get_json() or {}
    name = data.get("name")
    ip_address = data.get("ip_address")
    if not name or not ip_address:
        return jsonify({"error": "name and ip_address are required"}), 400

    team = Team(name=name, ip_address=ip_address)
    key_payload = data.get("ssh_private_key")
    if key_payload is None:
        key_payload = data.get("ssh_public_key")
    team.ssh_private_key = key_payload
    team.ssh_password = data.get("ssh_password")
    db.session.add(team)
    db.session.flush()
    credential = ensure_team_credentials(team)
    flag_tokens = []
    for challenge in Challenge.query.all():
        token = ensure_flag_access_token(team, challenge)
        flag_tokens.append(
            {
                "challenge_id": challenge.id,
                "challenge": challenge.name,
                "token": token.token,
            }
        )
    db.session.commit()

    return jsonify(
        {
            "id": team.id,
            "name": team.name,
            "ip_address": team.ip_address,
            "api_token": team.api_token,
            "portal_password": credential.password_plain,
            "flag_tokens": flag_tokens,
        }
    ), 201


@admin_bp.route("/teams/<int:team_id>/ssh-key", methods=["PUT"])
def update_team_key(team_id: int):
    require_admin()
    team = Team.query.get_or_404(team_id)
    data = request.get_json() or {}
    key_payload = data.get("ssh_private_key")
    if key_payload is None:
        key_payload = data.get("ssh_public_key")
    team.ssh_private_key = key_payload
    team.ssh_password = data.get("ssh_password") or team.ssh_password
    db.session.commit()
    return jsonify({"message": "SSH credentials updated"})


@admin_bp.route("/teams/<int:team_id>", methods=["DELETE"])
def delete_team(team_id: int):
    require_admin()
    team = Team.query.get_or_404(team_id)
    try:
        delete_team_record(team)
    except Exception:
        current_app.logger.exception("Failed to delete team %s", team_id)
        db.session.rollback()
        return jsonify({"error": "Failed to delete team"}), 500
    return jsonify({"message": "Team deleted"})


@admin_bp.route("/challenges", methods=["GET", "POST"])
def challenges():
    require_admin()
    if request.method == "GET":
        return jsonify(
            [
                {
                    "id": ch.id,
                    "name": ch.name,
                    "port": ch.port,
                    "sla_script": ch.sla_script,
                }
                for ch in Challenge.query.all()
            ]
        )

    data = request.get_json() or {}
    name = data.get("name")
    port = data.get("port")
    if not name or port is None:
        return jsonify({"error": "name and port are required"}), 400

    challenge = Challenge(
        name=name,
        port=int(port),
        sla_script=data.get("sla_script"),
    )
    db.session.add(challenge)
    db.session.flush()
    for team in Team.query.all():
        ensure_flag_access_token(team, challenge)
    db.session.commit()
    return (
        jsonify(
            {
                "id": challenge.id,
                "name": challenge.name,
                "port": challenge.port,
                "sla_script": challenge.sla_script,
            }
        ),
        201,
    )


@admin_bp.route("/rotate-flags", methods=["POST"])
def rotate_flags_view():
    require_admin()
    flags = rotate_flags()
    return jsonify({"message": "Flags rotated", "count": len(flags)})


@admin_bp.route("/sla", methods=["POST"])
def run_sla():
    require_admin()
    if event_has_ended():
        return (
            jsonify({"message": "Event has ended; SLA checks are disabled."}),
            409,
        )
    payload = request.get_json() or {}
    tick_number = int(payload.get("tick_number", 0))
    results = run_sla_checks(tick_number)
    return jsonify({"message": "SLA executed", "results": len(results)})


@admin_bp.route("/scoreboard", methods=["GET"])
def admin_scoreboard():
    require_admin()
    return jsonify(calculate_scores())
