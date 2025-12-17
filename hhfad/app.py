import os
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, render_template, render_template_string, request, send_file

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
RAW_LOG = LOG_DIR / "designer.log"
EVENT_LOG = LOG_DIR / "events.log"

BAD_FRAGMENTS = {"import", "subprocess", "popen", "exec", "eval", "os"}
BAD_PATTERN = re.compile(r"[;$`]")

FLAG_PATH = Path(os.environ.get("FLAG_PATH", BASE_DIR / "flag.txt"))


def guard_template(snippet: str) -> str:
    cleaned = snippet.strip()
    if not cleaned:
        raise ValueError("The template cannot be empty.")

    lowered = cleaned.lower()
    for frag in BAD_FRAGMENTS:
        if frag in lowered:
            raise ValueError(f"The word '{frag}' is blocked by our template filter.")

    if len(cleaned) > 800:
        raise ValueError("Keep the message under 800 characters.")

    if BAD_PATTERN.search(cleaned):
        raise ValueError("Meta characters ; $ ` are not allowed here.")

    return cleaned


def log_submission(user: str, payload: str) -> None:
    timestamp = datetime.utcnow().isoformat()
    raw_entry = f"[{timestamp}] {user}: {payload}\n"
    summary_entry = f"[{timestamp}] {user} updated preview ({len(payload)} chars)\n"

    with open(RAW_LOG, "a", encoding="utf-8") as handle:
        handle.write(raw_entry)

    with open(EVENT_LOG, "a", encoding="utf-8") as handle:
        handle.write(summary_entry)


def insecure_join(folder: Path, requested: str) -> Path:
    unquoted = urllib.parse.unquote(requested)
    cleaned = unquoted.replace("..", "").replace("\\", "")
    return folder / cleaned


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/designer", methods=["GET", "POST"])
def designer():
    snippet = request.values.get("snippet", "")
    preview_user = request.values.get("user", "helpful-guest")
    rendered = None
    error = None

    if request.method == "POST":
        try:
            safe_snippet = guard_template(snippet)
            preview_template = (
                "<article class='card'>"
                "<h3>Live preview for {{ preview_user|e }}</h3>"
                "<p class='hint'>Use Jinja to personalize the helper banner.</p>"
                f"{safe_snippet}"
                "</article>"
            )
            rendered = render_template_string(preview_template, preview_user=preview_user)
            log_submission(preview_user, snippet)
        except ValueError as exc:
            error = str(exc)
        except Exception as exc:  
            error = f"Template rendering error: {exc}"

    return render_template(
        "designer.html",
        snippet=snippet,
        rendered=rendered,
        error=error,
        preview_user=preview_user,
    )


@app.route("/logs")
def fetch_logs():
    name = request.args.get("name", "events.log")
    target = insecure_join(LOG_DIR, name)

    if not target.exists() or not target.is_file():
        abort(404, "Log not found")

    return send_file(target, mimetype="text/plain")


@app.route("/flag-check")
def flag_check():
    return {"status": "nope", "detail": "The flag never leaves the file system."}


@app.route("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8001)))
