"""Search for new public LinkedIn job posts and update feed/linkedin_posts.json.

Runs on a schedule in GitHub Actions, where the search API is reachable. The
app server then downloads the file instead of calling the search API itself.

    TAVILY_API_KEY=tvly-... python -m scripts.update_post_feed
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from matcher.post_offers import clean_post, fetch_web_posts, merge_posts

FEED_PATH = Path(__file__).resolve().parent.parent / "feed" / "linkedin_posts.json"
# Each role costs one search per run. Six roles, four runs a day, stays under
# Tavily's free 1,000 searches a month.
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
    found: list[dict] = []
    failures = 0
    for role in roles:
        posts, report, _searched = fetch_web_posts({"target_titles": [role], "location": location}, {})
        print(f"{role}: {report['count']} posts" + (f" ({report['error']})" if report["error"] else ""))
        if not report["ok"]:
            failures += 1
        found.extend(posts)
    if failures == len(roles):
        print("Every search failed. The feed was left as it was.")
        return 1

    existing = read_feed()
    posts = merge_posts([post for post in (clean_post(item) for item in found) if post], existing)
    if posts == existing:
        print("No new posts.")
        return 0
    FEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "posts": posts}
    FEED_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Feed now holds {len(posts)} posts.")
    return 0


def read_feed() -> list[dict]:
    try:
        payload = json.loads(FEED_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload.get("posts") if isinstance(payload, dict) else payload
    return [post for post in (clean_post(item) for item in items or []) if post]


if __name__ == "__main__":
    sys.exit(main())
