"""Local CV job matcher.

Finds open roles that fit a CV, prepares a short application letter, and
builds LinkedIn search links. Sending stays with the user: LinkedIn does not
allow third-party tools to log in and apply.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request, send_from_directory

from matcher.cv_parser import parse_cv, parse_upload
from matcher.job_sources import search_jobs
from matcher.linkedin_search import as_board_job, fetch_jobs_feed, fetch_linkedin_jobs, merge_jobs
from matcher.post_offers import fetch_feed_posts, fetch_web_posts, merge_posts, post_search_links, search_posts
from matcher.scorer import score_and_rank

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
POSTS_PATH = DATA_DIR / "linkedin_posts.json"
SEARCHES_PATH = DATA_DIR / "web_searches.json"
FEED_CHECK_PATH = DATA_DIR / "feed_checked.json"
FEED_URL = os.environ.get(
    "POSTS_FEED_URL",
    "https://raw.githubusercontent.com/IIshahub/JOB-Finder/main/feed/linkedin_posts.json",
).strip()
JOBS_PATH = DATA_DIR / "linkedin_jobs.json"
JOBS_FEED_CHECK_PATH = DATA_DIR / "jobs_feed_checked.json"
JOBS_FEED_URL = os.environ.get(
    "JOBS_FEED_URL",
    "https://raw.githubusercontent.com/IIshahub/JOB-Finder/main/feed/linkedin_jobs.json",
).strip()
FEED_INTERVAL = 3600

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
    linkedin_jobs, linkedin_report = refresh_linkedin_jobs(profile)
    jobs.extend(as_board_job(job) for job in linkedin_jobs)
    sources.append(linkedin_report)
    ranked = score_and_rank(profile, jobs, easy_apply=profile["easy_apply"])
    stored, web_report = refresh_posts(profile)
    posts, post_sources = search_posts(profile, stored)
    sources.extend(post_sources)
    if web_report:
        sources.append(web_report)
    return jsonify({"jobs": ranked, "sources": sources, "posts": posts, "post_searches": post_search_links(profile)})


@app.post("/api/posts")
def list_posts():
    payload = request.get_json(silent=True)
    profile = normalize_profile(payload if isinstance(payload, dict) else {})
    stored, _report = refresh_posts(profile) if FEED_URL else (saved_posts(), None)
    posts, _sources = search_posts(profile, stored)
    return jsonify({"posts": posts, "post_searches": post_search_links(profile)})


def refresh_posts(profile: dict) -> tuple[list[dict], dict | None]:
    """Add newly found public posts to the shared store and return it.

    With a feed URL, posts come from the scheduled GitHub job and the feed is
    downloaded at most once an hour. Without one, this server asks Tavily.
    """
    stored = saved_posts()
    if FEED_URL:
        checked = load_json(FEED_CHECK_PATH, {})
        last = checked.get("checked_at") if isinstance(checked, dict) else None
        if isinstance(last, (int, float)) and time.time() - last < FEED_INTERVAL:
            return stored, None
        save_json(FEED_CHECK_PATH, {"checked_at": time.time()})
        new_posts, report = fetch_feed_posts(FEED_URL)
    else:
        last_searched = load_json(SEARCHES_PATH, {})
        last_searched = last_searched if isinstance(last_searched, dict) else {}
        new_posts, report, searched = fetch_web_posts(profile, last_searched)
        if searched != last_searched:
            save_json(SEARCHES_PATH, searched)
    if new_posts:
        stored = merge_posts(new_posts, stored)
        save_json(POSTS_PATH, stored)
    return stored, report


def refresh_linkedin_jobs(profile: dict) -> tuple[list[dict], dict]:
    """Return saved LinkedIn jobs after adding any new ones.

    With a feed URL, jobs come from the scheduled GitHub job and the feed is
    downloaded at most once an hour. Without one, this server asks Tavily.
    """
    stored = saved_jobs()
    report = None
    if JOBS_FEED_URL:
        checked = load_json(JOBS_FEED_CHECK_PATH, {})
        last = checked.get("checked_at") if isinstance(checked, dict) else None
        if not (isinstance(last, (int, float)) and time.time() - last < FEED_INTERVAL):
            save_json(JOBS_FEED_CHECK_PATH, {"checked_at": time.time()})
            new_jobs, report = fetch_jobs_feed(JOBS_FEED_URL)
        else:
            new_jobs = []
    else:
        new_jobs, report = fetch_linkedin_jobs(profile)
    if new_jobs:
        stored = merge_jobs(new_jobs, stored)
        save_json(JOBS_PATH, stored)
    if report is None or report["ok"]:
        return stored, {"name": "LinkedIn jobs", "ok": True, "count": len(stored), "error": ""}
    return stored, {**report, "count": len(stored)}


def saved_jobs() -> list[dict]:
    saved = load_json(JOBS_PATH, [])
    return saved if isinstance(saved, list) else []


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
