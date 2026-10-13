"""Search for new public LinkedIn job posts and job listings and update the feeds.

Writes feed/linkedin_posts.json and feed/linkedin_jobs.json. Runs on a schedule
in GitHub Actions, where the search API is reachable. The app server then
downloads the files instead of calling the search API itself.

    TAVILY_API_KEY=tvly-... python -m scripts.update_post_feed
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from matcher.linkedin_search import clean_job, fetch_linkedin_jobs, merge_jobs
from matcher.post_offers import clean_post, fetch_web_posts, merge_posts

FEED_DIR = Path(__file__).resolve().parent.parent / "feed"
FEED_PATH = FEED_DIR / "linkedin_posts.json"
JOBS_FEED_PATH = FEED_DIR / "linkedin_jobs.json"
# Each role costs two searches per run, one for posts and one for jobs. Six
# roles, two runs a day, stays under Tavily's free 1,000 searches a month.
DEFAULT_ROLES = (
    "Frontend Developer",
    "Backend Developer",
    "Full Stack Developer",
    "React Developer",
    "Python Developer",
    "UI/UX Designer",
)


def main() -> int:
    roles = [role.strip() for role in os.environ.get("FEED_ROLES", "").split(",") if role.strip()] or list(DEFAULT_ROLES)
    location = os.environ.get("FEED_LOCATION", "Tehran, Iran")
    found_posts: list[dict] = []
    found_jobs: list[dict] = []
    failures = 0
    for role in roles:
        profile = {"target_titles": [role], "location": location}
        posts, report, _searched = fetch_web_posts(profile, {})
        print(f"{role}: {report['count']} posts" + (f" ({report['error']})" if report["error"] else ""))
        failures += not report["ok"]
        found_posts.extend(posts)
        jobs, report = fetch_linkedin_jobs(profile)
        print(f"{role}: {report['count']} jobs" + (f" ({report['error']})" if report["error"] else ""))
        failures += not report["ok"]
        found_jobs.extend(jobs)
    if failures == 2 * len(roles):
        print("Every search failed. The feeds were left as they were.")
        return 1

    existing = read_feed(FEED_PATH, "posts", clean_post)
    posts = merge_posts([post for post in (clean_post(item) for item in found_posts) if post], existing)
    write_feed(FEED_PATH, "posts", posts, existing)
    existing = read_feed(JOBS_FEED_PATH, "jobs", clean_job)
    jobs = merge_jobs([job for job in (clean_job(item) for item in found_jobs) if job], existing)
    write_feed(JOBS_FEED_PATH, "jobs", jobs, existing)
    return 0


def read_feed(path: Path, key: str, clean) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload.get(key) if isinstance(payload, dict) else payload
    return [item for item in (clean(entry) for entry in items or []) if item]


def write_feed(path: Path, key: str, items: list[dict], existing: list[dict]) -> None:
    if items == existing:
        print(f"No new {key}.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), key: items}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{path.name} now holds {len(items)} {key}.")


if __name__ == "__main__":
    sys.exit(main())
