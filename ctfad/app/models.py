from __future__ import annotations

from datetime import datetime
import secrets
from typing import Optional

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdminUser(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "admin_user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    active = db.Column("is_active", db.Boolean, default=True, nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, candidate: str) -> bool:
        return check_password_hash(self.password_hash, candidate)

    @property
    def is_active(self) -> bool:
        return bool(self.active)

    def get_id(self) -> str:
        return f"admin:{self.id}"

    @property
    def is_admin(self) -> bool:
        return True

    @property
    def is_team(self) -> bool:
        return False


class GameConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    tick_length = db.Column(db.Integer, nullable=False)
    num_ticks = db.Column(db.Integer, nullable=False)


class Team(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    ip_address = db.Column(db.String(64), unique=True, nullable=False)
    api_token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_hex(16))
    ssh_private_key = db.Column(db.Text, nullable=True)
    ssh_password = db.Column(db.String(128), nullable=True)

    flags = db.relationship("Flag", back_populates="team", cascade="all, delete-orphan")
    submissions = db.relationship("FlagSubmission", back_populates="attacker", foreign_keys="FlagSubmission.attacker_id")
    def_success = db.relationship("FlagSubmission", back_populates="defender", foreign_keys="FlagSubmission.defender_id")
    credential = db.relationship(
        "TeamCredential",
        back_populates="team",
        uselist=False,
        cascade="all, delete-orphan",
    )
    flag_access_tokens = db.relationship(
        "FlagAccessToken",
        back_populates="team",
        cascade="all, delete-orphan",
    )


class TeamCredential(UserMixin, db.Model):
    __tablename__ = "team_credential"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    password_plain = db.Column(db.String(64), nullable=False)

    team = db.relationship("Team", back_populates="credential")

    def set_password(self, password: str) -> None:
        self.password_plain = password
        self.password_hash = generate_password_hash(password)

    def check_password(self, candidate: str) -> bool:
        return check_password_hash(self.password_hash, candidate)

    def get_id(self) -> str:
        return f"team:{self.team_id}"

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_admin(self) -> bool:
        return False

    @property
    def is_team(self) -> bool:
        return True


class Challenge(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    port = db.Column(db.Integer, nullable=False)
    sla_script = db.Column(db.String(255), nullable=True)

    flags = db.relationship("Flag", back_populates="challenge", cascade="all, delete-orphan")
    flag_access_tokens = db.relationship(
        "FlagAccessToken",
        back_populates="challenge",
        cascade="all, delete-orphan",
    )


class Flag(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.String(255), nullable=False, unique=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenge.id"), nullable=False)

    team = db.relationship("Team", back_populates="flags")
    challenge = db.relationship("Challenge", back_populates="flags")


class FlagSubmission(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attacker_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    defender_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenge.id"), nullable=True)
    submitted_flag = db.Column(db.String(255), nullable=False)
    is_valid = db.Column(db.Boolean, default=False)

    attacker = db.relationship("Team", foreign_keys=[attacker_id], back_populates="submissions")
    defender = db.relationship("Team", foreign_keys=[defender_id], back_populates="def_success")
    challenge = db.relationship("Challenge")


class SLAResult(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenge.id"), nullable=False)
    passed = db.Column(db.Boolean, default=False)
    tick_number = db.Column(db.Integer, nullable=False)
    details = db.Column(db.Text, nullable=True)

    team = db.relationship("Team")
    challenge = db.relationship("Challenge")


def get_active_game_config() -> Optional[GameConfig]:
    return GameConfig.query.order_by(GameConfig.id.desc()).first()


def event_has_ended(reference_time: datetime | None = None) -> bool:
    """Return True when an active game config exists and the end time passed."""
    config = get_active_game_config()
    if not config or not config.end_time:
        return False
    reference = reference_time or datetime.utcnow()
    return reference >= config.end_time


from .extensions import login_manager


@login_manager.user_loader
def load_user(user_id: str) -> Optional[UserMixin]:
    if not user_id:
        return None
    try:
        kind, raw_id = user_id.split(":", 1)
    except ValueError:
        return None
    if not raw_id.isdigit():
        return None
    identifier = int(raw_id)
    if kind == "admin":
        return AdminUser.query.get(identifier)
    if kind == "team":
        return TeamCredential.query.filter_by(team_id=identifier).first()
    return None
class FlagAccessToken(db.Model):
    __tablename__ = "flag_access_token"
    __table_args__ = (
        db.UniqueConstraint("team_id", "challenge_id", name="uq_flag_access_token"),
    )

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenge.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_hex(16))

    team = db.relationship("Team", back_populates="flag_access_tokens")
    challenge = db.relationship("Challenge", back_populates="flag_access_tokens")
