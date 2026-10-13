"""Find LinkedIn job listings and hiring posts that mention a keyword.

    python -m scripts.search_linkedin "react developer" --location "Tehran, Iran"
    python -m scripts.search_linkedin "react developer" --remote

New results need a Tavily key in TAVILY_API_KEY (or --api-key). Without one,
only the saved posts in feed/ and data/ are searched. Where Tavily is blocked,
--remote runs the search in GitHub Actions through the gh CLI and saves what
it finds to data/ for the app.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from matcher.linkedin_search import TIME_RANGES, clean_job, merge_jobs, search_linkedin
from matcher.post_offers import clean_post, merge_posts

ROOT = Path(__file__).resolve().parent.parent
DATA_POSTS = ROOT / "data" / "linkedin_posts.json"
DATA_JOBS = ROOT / "data" / "linkedin_jobs.json"
SAVED_POSTS = (ROOT / "feed" / "linkedin_posts.json", DATA_POSTS)
WORKFLOW = "linkedin-search.yml"
ARTIFACT = "linkedin-search"
REMOTE_WAIT = 300


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search LinkedIn jobs and hiring posts for a keyword.")
    parser.add_argument("keyword", nargs="+", help="words that must appear, for example: react developer")
    parser.add_argument("-l", "--location", default="", help='city or country, for example: "Tehran, Iran"')
    parser.add_argument("--since", choices=TIME_RANGES, default="month", help="how far back to search (default: month)")
    parser.add_argument("--api-key", default="", help="Tavily key; defaults to the TAVILY_API_KEY variable")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="only search saved posts")
    mode.add_argument("--remote", action="store_true", help="run the search in GitHub Actions and save the results to data/")
    parser.add_argument("--limit", type=int, default=30, help="most results to print per section (default: 30)")
    parser.add_argument("--json", type=Path, help="also write every result to this file")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    keyword = " ".join(args.keyword)
    if args.remote:
        try:
            result = remote_search(keyword, args.location, args.since)
        except RuntimeError as exc:
            print(f"Remote search failed: {exc}", file=sys.stderr)
            return 2
        jobs, posts = save_remote_results(result)
        print(f"data/ now holds {jobs} LinkedIn jobs and {posts} posts for the app.\n")
    else:
        result = search_linkedin(
            keyword,
            location=args.location,
            since=args.since,
            api_key=args.api_key,
            saved_posts=read_saved_posts(),
            offline=args.offline,
        )

    print_section("LinkedIn jobs", result["jobs"], args.limit)
    print_section("LinkedIn posts", result["posts"], args.limit)
    print("Sources")
    for report in result["reports"]:
        status = f"{report['count']} found" if report["ok"] else report["error"]
        print(f"  {report['name']}: {status}")
    print()
    print("Signed-in LinkedIn searches")
    print(f"  Jobs:  {result['links']['jobs']}")
    print(f"  Posts: {result['links']['posts']}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nSaved {len(result['jobs'])} jobs and {len(result['posts'])} posts to {args.json}")
    return 0 if result["jobs"] or result["posts"] else 1


def remote_search(keyword: str, location: str, since: str) -> dict:
    request_id = uuid.uuid4().hex[:10]
    gh(
        "workflow", "run", WORKFLOW,
        "-f", f"keyword={keyword}",
        "-f", f"location={location}",
        "-f", f"since={since}",
        "-f", f"request_id={request_id}",
    )
    print("Searching in GitHub Actions. This usually takes about a minute...", flush=True)
    deadline = time.monotonic() + REMOTE_WAIT
    run_id = None
    while time.monotonic() < deadline:
        time.sleep(5)
        if run_id is None:
            runs = json.loads(gh("run", "list", "--workflow", WORKFLOW, "--limit", "20", "--json", "databaseId,displayTitle"))
            run_id = next((run["databaseId"] for run in runs if f"[{request_id}]" in run["displayTitle"]), None)
            continue
        state = json.loads(gh("run", "view", str(run_id), "--json", "status,conclusion,url"))
        if state["status"] != "completed":
            continue
        if state["conclusion"] != "success":
            raise RuntimeError(f"the GitHub run ended with '{state['conclusion']}'. See {state['url']}")
        with tempfile.TemporaryDirectory() as folder:
            gh("run", "download", str(run_id), "-n", ARTIFACT, "-D", folder)
            return json.loads((Path(folder) / "linkedin_search.json").read_text(encoding="utf-8"))
    where = f" Check run {run_id} on GitHub." if run_id else ""
    raise RuntimeError(f"the GitHub run did not finish within {REMOTE_WAIT} seconds.{where}")


def gh(*args: str) -> str:
    try:
        done = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
    except FileNotFoundError:
        raise RuntimeError("install the GitHub CLI (gh) and run 'gh auth login' first.") from None
    if done.returncode != 0:
        lines = (done.stderr or done.stdout).strip().splitlines()
        raise RuntimeError(lines[-1] if lines else f"gh {args[0]} failed.")
    return done.stdout


def save_remote_results(result: dict) -> tuple[int, int]:
    jobs = [job for job in (clean_job(item) for item in result.get("jobs") or []) if job]
    jobs = merge_jobs(jobs, read_list(DATA_JOBS, clean_job))
    posts = [post for post in (clean_post(item) for item in result.get("posts") or []) if post]
    posts = merge_posts(posts, read_list(DATA_POSTS, clean_post))
    DATA_JOBS.parent.mkdir(parents=True, exist_ok=True)
    DATA_JOBS.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")
    DATA_POSTS.write_text(json.dumps(posts, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(jobs), len(posts)


def read_list(path: Path, clean) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in (clean(entry) for entry in payload) if item]


def read_saved_posts() -> list[dict]:
    posts = []
    for path in SAVED_POSTS:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items = payload.get("posts") if isinstance(payload, dict) else payload
        posts.extend(post for post in (clean_post(item) for item in items or []) if post)
    return posts


def print_section(name: str, items: list[dict], limit: int) -> None:
    print(f"{name} ({len(items)})")
    if not items:
        print("  Nothing matched.\n")
        return
    for item in items[:limit]:
        details = " · ".join(part for part in (item.get("company"), item.get("location"), item.get("published")) if part)
        print(f"- {item['title']}")
        if details:
            print(f"  {details}")
        if item.get("apply_email"):
            print(f"  Email: {item['apply_email']}")
        print(f"  {item['url']}")
    if len(items) > limit:
        print(f"  ...and {len(items) - limit} more. Use --limit or --json to see them all.")
    print()


if __name__ == "__main__":
    sys.exit(main())
