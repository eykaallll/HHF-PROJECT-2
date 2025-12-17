from __future__ import annotations

from datetime import timedelta
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, url_for, current_app
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from ..forms import (
    ChallengeForm,
    ChallengeUpdateForm,
    DeleteTeamForm,
    GameConfigForm,
    RotateFlagsForm,
    SLAForm,
    TeamForm,
    TeamKeyForm,
)
from ..models import (
    Challenge,
    FlagSubmission,
    GameConfig,
    SLAResult,
    Team,
    event_has_ended,
    get_active_game_config,
)
from ..services import (
    calculate_scores,
    delete_team as delete_team_record,
    ensure_flag_access_token,
    ensure_team_credentials,
    rotate_flags,
    run_sla_checks,
)
from ..extensions import db

admin_ui_bp = Blueprint("admin_ui", __name__, url_prefix="/admin/ui")


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not getattr(current_user, "is_admin", False):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@admin_ui_bp.route("/")
@admin_required
def dashboard():
    scoreboard = calculate_scores()
    total_flags = FlagSubmission.query.filter_by(is_valid=True).count()
    recent_attacks = (
        FlagSubmission.query.order_by(FlagSubmission.created_at.desc()).limit(10).all()
    )
    sla_logs = SLAResult.query.order_by(SLAResult.created_at.desc()).limit(10).all()
    config = get_active_game_config()
    challenge_count = Challenge.query.count()
    rotate_form = RotateFlagsForm()
    sla_form = SLAForm()
    return render_template(
        "admin/dashboard.html",
        scoreboard=scoreboard,
        total_flags=total_flags,
        recent_attacks=recent_attacks,
        sla_logs=sla_logs,
        config=config,
        challenge_count=challenge_count,
        rotate_form=rotate_form,
        sla_form=sla_form,
    )


@admin_ui_bp.route("/rotate-flags", methods=["POST"])
@admin_required
def rotate_flags_action():
    form = RotateFlagsForm()
    if form.validate_on_submit():
        updated = rotate_flags()
        flash(f"Rotated {len(updated)} flags", "success")
    else:
        flash("Failed to rotate flags", "danger")
    return redirect(url_for("admin_ui.dashboard"))


@admin_ui_bp.route("/run-sla", methods=["POST"])
@admin_required
def run_sla_action():
    form = SLAForm()
    if form.validate_on_submit():
        if event_has_ended():
            flash("Event has ended; SLA checks are disabled.", "warning")
            return redirect(url_for("admin_ui.dashboard"))
        results = run_sla_checks(form.tick_number.data)
        flash(f"Executed {len(results)} SLA checks", "success")
    else:
        flash("Failed to execute SLA checks", "danger")
    return redirect(url_for("admin_ui.dashboard"))


@admin_ui_bp.route("/teams", methods=["GET", "POST"])
@admin_required
def teams():
    form = TeamForm()
    teams = Team.query.order_by(Team.name.asc()).all()
    challenges = Challenge.query.order_by(Challenge.name.asc()).all()
    key_forms: dict[int, TeamKeyForm] = {}
    delete_form = DeleteTeamForm()
    if form.validate_on_submit():
        team = Team(
            name=form.name.data.strip(),
            ip_address=form.ip_address.data.strip(),
        )
        team.ssh_password = form.ssh_password.data or None
        db.session.add(team)
        try:
            db.session.flush()
            ensure_team_credentials(team)
            db.session.commit()
            flash(
                f"Created team {team.name} - portal password: {team.credential.password_plain}",
                "success",
            )
            return redirect(url_for("admin_ui.teams"))
        except IntegrityError:
            db.session.rollback()
            flash("Team name or IP already exists", "danger")
    created_tokens = False
    for team in teams:
        key_form = TeamKeyForm(formdata=None)
        key_form.team_id.data = str(team.id)
        key_form.ssh_password.data = team.ssh_password or ""
        key_forms[team.id] = key_form
        for challenge in challenges:
            if any(token.challenge_id == challenge.id for token in team.flag_access_tokens):
                continue
            ensure_flag_access_token(team, challenge)
            created_tokens = True
    if created_tokens:
        db.session.commit()
        teams = Team.query.order_by(Team.name.asc()).all()
    return render_template(
        "admin/teams.html",
        form=form,
        teams=teams,
        key_forms=key_forms,
        challenges=challenges,
        delete_form=delete_form,
    )


@admin_ui_bp.route("/teams/<int:team_id>/ssh-key", methods=["POST"])
@admin_required
def update_team_key(team_id: int):
    form = TeamKeyForm()
    if form.validate_on_submit():
        try:
            submitted_id = int(form.team_id.data)
        except (TypeError, ValueError):
            submitted_id = None
        if submitted_id == team_id:
            team = Team.query.get_or_404(team_id)
            team.ssh_password = form.ssh_password.data or None
            db.session.commit()
            flash(f"Updated SSH password for {team.name}", "success")
            return redirect(url_for("admin_ui.teams"))
    flash("Unable to update SSH password", "danger")
    return redirect(url_for("admin_ui.teams"))


@admin_ui_bp.route("/teams/<int:team_id>/delete", methods=["POST"])
@admin_required
def delete_team(team_id: int):
    form = DeleteTeamForm()
    if form.validate_on_submit():
        try:
            submitted_id = int(form.team_id.data)
        except (TypeError, ValueError):
            submitted_id = None
        if submitted_id == team_id:
            team = Team.query.get_or_404(team_id)
            try:
                delete_team_record(team)
                flash(f"Deleted team {team.name}", "success")
                return redirect(url_for("admin_ui.teams"))
            except Exception:
                current_app.logger.exception("Failed to delete team %s from UI", team_id)
                db.session.rollback()
                flash("Unable to delete team due to a server error.", "danger")
                return redirect(url_for("admin_ui.teams"))
    flash("Unable to delete team", "danger")
    return redirect(url_for("admin_ui.teams"))


@admin_ui_bp.route("/challenges", methods=["GET", "POST"])
@admin_required
def challenges():
    form = ChallengeForm()
    challenges = Challenge.query.order_by(Challenge.name.asc()).all()
    edit_forms: dict[int, ChallengeUpdateForm] = {}
    for challenge in challenges:
        edit_form = ChallengeUpdateForm(formdata=None, obj=challenge)
        edit_form.challenge_id.data = str(challenge.id)
        edit_forms[challenge.id] = edit_form
    if form.validate_on_submit():
        challenge = Challenge(
            name=form.name.data.strip(),
            port=form.port.data,
            sla_script=form.sla_script.data or None,
        )
        db.session.add(challenge)
        try:
            db.session.flush()
            for team in Team.query.all():
                ensure_flag_access_token(team, challenge)
            db.session.commit()
            flash(f"Created challenge {challenge.name}", "success")
            return redirect(url_for("admin_ui.challenges"))
        except IntegrityError:
            db.session.rollback()
            flash("Challenge name must be unique", "danger")
    return render_template(
        "admin/challenges.html",
        form=form,
        challenges=challenges,
        edit_forms=edit_forms,
    )


@admin_ui_bp.route("/challenges/<int:challenge_id>/edit", methods=["POST"])
@admin_required
def edit_challenge(challenge_id: int):
    form = ChallengeUpdateForm()
    if form.validate_on_submit():
        try:
            submitted_id = int(form.challenge_id.data)
        except (TypeError, ValueError):
            submitted_id = None
        if submitted_id != challenge_id:
            flash("Challenge identifier mismatch", "danger")
            return redirect(url_for("admin_ui.challenges"))
        challenge = Challenge.query.get_or_404(challenge_id)
        challenge.name = form.name.data.strip()
        challenge.port = form.port.data
        challenge.sla_script = form.sla_script.data or None
        try:
            db.session.commit()
            flash(f"Updated challenge {challenge.name}", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Challenge name must be unique", "danger")
        return redirect(url_for("admin_ui.challenges"))
    flash("Failed to update challenge", "danger")
    return redirect(url_for("admin_ui.challenges"))


@admin_ui_bp.route("/config", methods=["GET", "POST"])
@admin_required
def configure():
    config = get_active_game_config()
    form = GameConfigForm()
    if not form.is_submitted() and config:
        form.start_time.data = config.start_time
        form.end_time.data = config.end_time
        form.tick_length.data = config.tick_length
        form.num_ticks.data = config.num_ticks
    if form.validate_on_submit():
        computed_end_time = form.end_time.data
        if (
            form.start_time.data
            and form.tick_length.data
            and form.num_ticks.data
        ):
            total_seconds = form.tick_length.data * form.num_ticks.data
            computed_end_time = form.start_time.data + timedelta(seconds=total_seconds)
            form.end_time.data = computed_end_time
        new_config = GameConfig(
            start_time=form.start_time.data,
            end_time=computed_end_time,
            tick_length=form.tick_length.data,
            num_ticks=form.num_ticks.data,
        )
        db.session.add(new_config)
        db.session.commit()
        flash("Game configuration saved", "success")
        return redirect(url_for("admin_ui.configure"))
    return render_template("admin/config.html", form=form, config=config)
