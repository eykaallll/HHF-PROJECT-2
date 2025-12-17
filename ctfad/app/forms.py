from __future__ import annotations

from datetime import datetime

from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, HiddenField, IntegerField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class LoginForm(FlaskForm):
    username = StringField(
        "Username or Team Name", validators=[DataRequired(), Length(max=120)]
    )
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Sign In")


class TeamForm(FlaskForm):
    name = StringField("Team Name", validators=[DataRequired(), Length(max=120)])
    ip_address = StringField("Service IP", validators=[DataRequired(), Length(max=64)])
    ssh_password = StringField("SSH Password", validators=[Optional(), Length(max=128)])
    submit = SubmitField("Create Team")


class TeamKeyForm(FlaskForm):
    team_id = HiddenField(validators=[DataRequired()])
    ssh_password = StringField("SSH Password", validators=[Optional(), Length(max=128)])
    submit = SubmitField("Update Key")


class DeleteTeamForm(FlaskForm):
    team_id = HiddenField(validators=[DataRequired()])
    submit = SubmitField("Delete Team")


class ChallengeForm(FlaskForm):
    name = StringField("Challenge Name", validators=[DataRequired(), Length(max=120)])
    port = IntegerField("Service Port", validators=[DataRequired(), NumberRange(min=1, max=65535)])
    sla_script = StringField("SLA Script Path", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Create Challenge")


class ChallengeUpdateForm(FlaskForm):
    challenge_id = HiddenField(validators=[DataRequired()])
    name = StringField("Challenge Name", validators=[DataRequired(), Length(max=120)])
    port = IntegerField("Service Port", validators=[DataRequired(), NumberRange(min=1, max=65535)])
    sla_script = StringField("SLA Script Path", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Save Changes")


class GameConfigForm(FlaskForm):
    start_time = DateTimeLocalField(
        "Start Time",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired()],
        default=datetime.utcnow,
    )
    end_time = DateTimeLocalField(
        "End Time",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired()],
    )
    tick_length = IntegerField(
        "Tick Length (seconds)",
        validators=[DataRequired(), NumberRange(min=30, max=86400)],
    )
    num_ticks = IntegerField(
        "Number of Ticks",
        validators=[DataRequired(), NumberRange(min=1, max=1000)],
    )
    submit = SubmitField("Save Configuration")


class RotateFlagsForm(FlaskForm):
    submit = SubmitField("Rotate Flags")


class SLAForm(FlaskForm):
    tick_number = IntegerField(
        "Tick Number",
        validators=[DataRequired(), NumberRange(min=0, max=100000)],
        default=0,
    )
    submit = SubmitField("Run SLA Checks")
