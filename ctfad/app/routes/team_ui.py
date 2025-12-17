from __future__ import annotations

from functools import wraps

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user

team_ui_bp = Blueprint("team_ui", __name__, url_prefix="/team")


def team_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, "is_team", False):
            next_dest = request.path if request.method == "GET" else None
            if next_dest:
                return redirect(url_for("auth.login", next=next_dest))
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


@team_ui_bp.route("/dashboard")
@team_required
def dashboard():
    team = current_user.team
    return render_template("team/dashboard.html", team=team)
