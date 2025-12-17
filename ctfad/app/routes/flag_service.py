from __future__ import annotations

from flask import Blueprint, abort, jsonify

from ..models import Flag, FlagAccessToken

flag_service_bp = Blueprint("flag_service", __name__, url_prefix="/service")


@flag_service_bp.route("/flag/<string:token>", methods=["GET"])
def fetch_flag(token: str):
    credential = FlagAccessToken.query.filter_by(token=token).one_or_none()
    if credential is None:
        abort(404, description="Unknown flag token")

    flag = Flag.query.filter_by(team_id=credential.team_id, challenge_id=credential.challenge_id).one_or_none()
    if flag is None:
        abort(404, description="Flag not available")

    return jsonify(
        {
            "team": credential.team.name if credential.team else None,
            "challenge": credential.challenge.name if credential.challenge else None,
            "flag": flag.value,
            "updated_at": flag.updated_at.isoformat() if getattr(flag, "updated_at", None) else None,
        }
    )
