"""Local CV job matcher.

Finds open roles that fit a CV, prepares a short application letter, and
builds LinkedIn search links. Sending stays with the user: LinkedIn does not
allow third-party tools to log in and apply.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request, send_from_directory

from matcher.cv_parser import parse_cv, parse_upload
from matcher.job_sources import search_jobs
from matcher.post_offers import post_search_links, search_posts
from matcher.scorer import score_and_rank

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
PROFILE_PATH = DATA_DIR / "profile.json"
APPLICATIONS_PATH = DATA_DIR / "applications.json"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@app.before_request
def block_cross_site_writes():
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None
    origin = request.headers.get("Origin", "")
    if origin:
        if not is_local_origin(origin):
            return jsonify({"error": "This app only accepts requests from this computer."}), 403
        return None
    site = request.headers.get("Sec-Fetch-Site", "")
    if site in {"cross-site", "same-site"}:
        return jsonify({"error": "This app only accepts requests from this computer."}), 403
    return None


def is_local_origin(origin: str) -> bool:
    parsed = urlparse(origin)
    return parsed.scheme in {"http", "https"} and parsed.hostname in LOCAL_HOSTS


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon")


@app.get("/api/profile")
def get_profile():
    return jsonify({"profile": load_json(PROFILE_PATH, None)})


@app.post("/api/parse")
def parse():
    upload = request.files.get("file")
    if upload and upload.filename:
        try:
            profile = parse_upload(upload.filename, upload.read())
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            return jsonify({"error": "That file could not be read. Try PDF, DOCX, or paste the text."}), 400
    else:
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text") or request.form.get("text") or "").strip()
        if len(text) < 40:
            return jsonify({"error": "Paste more of your CV so there is enough to match."}), 400
        profile = parse_cv(text)
        profile["cv_filename"] = "Pasted CV"
    profile = normalize_profile(profile)
    save_json(PROFILE_PATH, profile)
    return jsonify({"profile": profile})


@app.post("/api/search")
def search():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Send your profile as JSON."}), 400
    profile = normalize_profile(payload)
    if not profile["target_titles"]:
        return jsonify({"error": "Add at least one role to search for."}), 400
    save_json(PROFILE_PATH, profile)
    jobs, sources = search_jobs(profile["target_titles"])
    ranked = score_and_rank(profile, jobs, easy_apply=profile["easy_apply"])
    posts, post_sources = search_posts(profile)
    sources.extend(post_sources)
    return jsonify({"jobs": ranked, "sources": sources, "posts": posts, "post_searches": post_search_links(profile)})


@app.get("/api/posts")
def list_posts():
    profile = load_json(PROFILE_PATH, {}) or {}
    if not isinstance(profile, dict):
        profile = {}
    posts, _sources = search_posts(profile)
    return jsonify({"posts": posts, "post_searches": post_search_links(profile)})


@app.get("/api/applications")
def list_applications():
    saved = load_json(APPLICATIONS_PATH, [])
    if not isinstance(saved, list):
        saved = []
    return jsonify({"applications": saved})


@app.post("/api/applications")
def save_application():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload.get("id"):
        return jsonify({"error": "Missing application."}), 400
    saved = load_json(APPLICATIONS_PATH, [])
    if not isinstance(saved, list):
        saved = []
    record = {
        "id": str(payload.get("id"))[:40],
        "title": clip(payload.get("title"), 140),
        "company": clip(payload.get("company"), 140),
        "url": http_url(payload.get("url"), 500),
        "source": clip(payload.get("source"), 40),
        "score": bounded_int(payload.get("score")),
        "cover_letter": str(payload.get("cover_letter") or "")[:5000],
        "linkedin_search_url": http_url(payload.get("linkedin_search_url"), 800),
        "apply_email": email_address(payload.get("apply_email")),
        "saved_at": timestamp(),
        "status": "prepared",
    }
    saved = [item for item in saved if item.get("id") != record["id"]]
    saved.insert(0, record)
    save_json(APPLICATIONS_PATH, saved[:100])
    return jsonify({"application": record})


@app.delete("/api/applications/<application_id>")
def delete_application(application_id: str):
    saved = load_json(APPLICATIONS_PATH, [])
    if not isinstance(saved, list):
        saved = []
    saved = [item for item in saved if item.get("id") != application_id]
    save_json(APPLICATIONS_PATH, saved)
    return jsonify({"ok": True})


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "That file is larger than 5 MB."}), 413


def normalize_profile(payload: dict) -> dict:
    return {
        "name": clip(payload.get("name"), 80),
        "email": clip(payload.get("email"), 120),
        "phone": clip(payload.get("phone"), 40),
        "location": clip(payload.get("location"), 80),
        "all_countries": as_bool(payload.get("all_countries")),
        "linkedin": clip(payload.get("linkedin"), 200),
        "summary": clip(payload.get("summary"), 600, collapse=False),
        "skills": clean_list(payload.get("skills"), limit=40, item_limit=40),
        "target_titles": clean_list(payload.get("target_titles"), limit=6, item_limit=80),
        "target_regions": clean_list(payload.get("target_regions"), limit=24, item_limit=40),
        "cv_text": str(payload.get("cv_text") or "")[:200000],
        "cv_filename": clip(payload.get("cv_filename"), 120),
        "remote_only": as_bool(payload.get("remote_only")),
        "easy_apply": as_bool(payload.get("easy_apply", True)),
    }


def clean_list(values, limit: int, item_limit: int) -> list[str]:
    if isinstance(values, str):
        values = re.split(r"[,;\n]", values)
    if not isinstance(values, list):
        return []
    seen = set()
    cleaned = []
    for value in values:
        item = clip(value, item_limit)
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
        if len(cleaned) >= limit:
            break
    return cleaned


def clip(value, limit: int, collapse: bool = True) -> str:
    text = str(value or "").strip()
    if collapse:
        text = " ".join(text.split())
    return text[:limit]


def bounded_int(value, low: int = 0, high: int = 100) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(low, min(high, number))


def email_address(value) -> str:
    text = clip(value, 160)
    if re.fullmatch(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I):
        return text
    return ""


def http_url(value, limit: int) -> str:
    text = clip(value, limit)
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return text
    return ""


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Open http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050, debug=False)
