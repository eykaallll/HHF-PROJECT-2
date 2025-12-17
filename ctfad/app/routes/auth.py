from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..forms import LoginForm
from ..models import AdminUser, Team

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if getattr(current_user, "is_admin", False):
            return redirect(url_for("admin_ui.dashboard"))
        if getattr(current_user, "is_team", False):
            flash("You are already signed in as a team.", "info")
            return redirect(url_for("team_ui.dashboard"))
        return redirect(url_for("public.home"))

    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.username.data.strip()
        password = form.password.data
        if identifier.lower() == "admin":
            user = AdminUser.query.filter_by(username="admin").first()
            if user and user.check_password(password) and user.is_active:
                login_user(user)
                flash("Logged in successfully", "success")
                next_page = request.args.get("next")
                return redirect(next_page or url_for("admin_ui.dashboard"))
        else:
            team = Team.query.filter_by(name=identifier).first()
            credential = team.credential if team else None
            if credential and credential.check_password(password):
                login_user(credential)
                flash("Signed in successfully", "success")
                next_page = request.args.get("next")
                return redirect(next_page or url_for("team_ui.dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("admin/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out", "info")
    return redirect(url_for("auth.login"))
