from __future__ import annotations

import os
import threading
import time

from flask import Flask
from sqlalchemy import inspect, text
from sqlalchemy.engine.reflection import Inspector

from .config import Config
from .extensions import db, login_manager
from .routes.admin import admin_bp
from .routes.admin_ui import admin_ui_bp
from .routes.auth import auth_bp
from .routes.flag_service import flag_service_bp
from .routes.player import player_bp
from .routes.public import public_bp
from .routes.team_ui import team_ui_bp
from .models import AdminUser, Challenge, Team
from .services import (
    ensure_flag_access_token,
    ensure_team_credentials,
    rotate_flags,
    run_sla_checks,
)


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    with app.app_context():
        db.create_all()
        _ensure_schema_updates()
        dirty = False
        if not AdminUser.query.filter_by(username="admin").first():
            admin = AdminUser(username="admin")
            admin.set_password("admin#321")
            db.session.add(admin)
            dirty = True
        challenges = list(Challenge.query.all())
        for team in Team.query.all():
            if team.credential is None:
                ensure_team_credentials(team)
                dirty = True
            for challenge in challenges:
                if any(token.challenge_id == challenge.id for token in team.flag_access_tokens):
                    continue
                ensure_flag_access_token(team, challenge)
                dirty = True
        if dirty:
            db.session.commit()

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_ui_bp)
    app.register_blueprint(flag_service_bp)
    app.register_blueprint(team_ui_bp)
    app.register_blueprint(player_bp)
    app.register_blueprint(public_bp)
    _maybe_start_flag_rotation_worker(app)
    _maybe_start_sla_worker(app)

    return app


def _maybe_start_flag_rotation_worker(app: Flask) -> None:
    if not app.config.get("AUTO_FLAG_ROTATION"):
        return
    interval = int(app.config.get("FLAG_ROTATION_INTERVAL", 0))
    if interval <= 0:
        return
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        is_reloader_child = True
    else:
        is_reloader_child = False
    if app.config.get("ENV") == "development" and not is_reloader_child:
        return

    if app.extensions.get("flag_rotation_thread"):
        return

    with app.app_context():
        rotated_now = rotate_flags()
        app.logger.info("Initial auto-rotation completed (%s flags)", len(rotated_now))

    def worker() -> None:
        with app.app_context():
            while True:
                time.sleep(interval)
                rotated = rotate_flags()
                app.logger.info("Auto-rotated %s flags", len(rotated))

    thread = threading.Thread(target=worker, daemon=True, name="flag-rotation-worker")
    thread.start()
    app.extensions["flag_rotation_thread"] = thread
    app.logger.info("Started automatic flag rotation thread (interval=%ss)", interval)


def _maybe_start_sla_worker(app: Flask) -> None:
    if not app.config.get("AUTO_SLA_CHECKS"):
        return
    tick_length = int(app.config.get("SLA_TICK_LENGTH", 0))
    if tick_length <= 0:
        return
    offset = int(app.config.get("SLA_PRECHECK_OFFSET", 20))
    offset = max(1, min(offset, tick_length - 1))
    is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if app.config.get("ENV") == "development" and not is_reloader_child:
        return
    if app.extensions.get("sla_worker_thread"):
        return

    def worker() -> None:
        tick_number = 0
        next_tick_start = time.time()
        with app.app_context():
            while True:
                now = time.time()
                delay = next_tick_start - now
                if delay > 0:
                    time.sleep(delay)
                tick_number += 1
                app.logger.info("Auto SLA: running start-of-tick checks (tick=%s)", tick_number)
                results = run_sla_checks(tick_number)
                failing_pairs = [(res.team_id, res.challenge_id) for res in results if not res.passed]
                precheck_time = next_tick_start + tick_length - offset
                next_tick_start += tick_length
                if failing_pairs:
                    now = time.time()
                    delay = precheck_time - now
                    if delay > 0:
                        time.sleep(delay)
                    retry_pairs: list[tuple[Team, Challenge]] = []
                    for team_id, challenge_id in failing_pairs:
                        team = Team.query.get(team_id)
                        challenge = Challenge.query.get(challenge_id)
                        if team and challenge:
                            retry_pairs.append((team, challenge))
                    if not retry_pairs:
                        continue
                    app.logger.info(
                        "Auto SLA: re-running %s failing pairs before tick %s ends",
                        len(retry_pairs),
                        tick_number,
                    )
                    run_sla_checks(tick_number, pairs=retry_pairs)

    thread = threading.Thread(target=worker, daemon=True, name="sla-worker")
    thread.start()
    app.extensions["sla_worker_thread"] = thread
    app.logger.info(
        "Started automatic SLA worker (tick_length=%ss, precheck_offset=%ss)", tick_length, offset
    )


def _ensure_schema_updates() -> None:
    inspector = inspect(db.engine)
    columns = {col["name"] for col in inspector.get_columns("sla_result")}
    if "details" not in columns:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE sla_result ADD COLUMN details TEXT"))
        db.session.commit()
    _ensure_team_private_key_column(inspector)
    _ensure_team_ssh_password_column(inspector)


def _ensure_team_private_key_column(inspector: Inspector) -> None:
    team_columns = {col["name"] for col in inspector.get_columns("team")}
    if "ssh_private_key" in team_columns:
        return
    if "ssh_public_key" not in team_columns:
        return
    dialect = db.engine.dialect.name
    if dialect == "mysql":
        statement = "ALTER TABLE team CHANGE COLUMN ssh_public_key ssh_private_key TEXT"
    else:
        statement = "ALTER TABLE team RENAME COLUMN ssh_public_key TO ssh_private_key"
    with db.engine.connect() as conn:
        conn.execute(text(statement))
    db.session.commit()


def _ensure_team_ssh_password_column(inspector: Inspector) -> None:
    team_columns = {col["name"] for col in inspector.get_columns("team")}
    if "ssh_password" in team_columns:
        return
    with db.engine.connect() as conn:
        conn.execute(text("ALTER TABLE team ADD COLUMN ssh_password VARCHAR(128)"))
    db.session.commit()
