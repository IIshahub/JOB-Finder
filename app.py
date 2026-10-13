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
from matcher.post_offers import fetch_web_posts, merge_posts, post_search_links, search_posts
from matcher.scorer import score_and_rank

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
POSTS_PATH = DATA_DIR / "linkedin_posts.json"

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
            return jsonify({"error": "This app only accepts requests from its own address."}), 403
        return None
    site = request.headers.get("Sec-Fetch-Site", "")
    if site in {"cross-site", "same-site"}:
        return jsonify({"error": "This app only accepts requests from its own address."}), 403
    return None


def is_local_origin(origin: str) -> bool:
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    return hostname in LOCAL_HOSTS or hostname == current_hostname()


def current_hostname() -> str:
    host = (request.host or "").strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end != -1 else host
    return host.split(":", 1)[0]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon")


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
    return jsonify({"profile": profile})


@app.post("/api/search")
def search():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Send your profile as JSON."}), 400
    profile = normalize_profile(payload)
    if not profile["target_titles"]:
        return jsonify({"error": "Add at least one role to search for."}), 400
    jobs, sources = search_jobs(profile["target_titles"])
    ranked = score_and_rank(profile, jobs, easy_apply=profile["easy_apply"])
    web_posts, web_report = fetch_web_posts(profile)
    stored = merge_posts(web_posts, saved_posts())
    if web_posts:
        save_json(POSTS_PATH, stored)
    posts, post_sources = search_posts(profile, stored)
    sources.extend(post_sources)
    sources.append(web_report)
    return jsonify({"jobs": ranked, "sources": sources, "posts": posts, "post_searches": post_search_links(profile)})


@app.post("/api/posts")
def list_posts():
    payload = request.get_json(silent=True)
    profile = normalize_profile(payload if isinstance(payload, dict) else {})
    posts, _sources = search_posts(profile, saved_posts())
    return jsonify({"posts": posts, "post_searches": post_search_links(profile)})


def saved_posts() -> list[dict]:
    saved = load_json(POSTS_PATH, [])
    return saved if isinstance(saved, list) else []


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


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("Open http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050, debug=False)
