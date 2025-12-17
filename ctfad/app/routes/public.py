from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for

public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def home():
    return render_template("index.html")


@public_bp.route("/api-docs")
def api_docs():
    return render_template("api_docs.html")


@public_bp.route("/scoreboard")
def scoreboard():
    return render_template("scoreboard.html")


@public_bp.route("/attack-log")
def attack_log():
    return render_template("attack_log.html")


@public_bp.route("/ssh-guide")
def ssh_guide():
    return render_template("ssh_guide.html")


@public_bp.route("/attack-map")
def attack_map():
    return redirect(url_for("public.attack_log"))
