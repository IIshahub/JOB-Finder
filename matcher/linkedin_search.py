"""Search LinkedIn job listings and hiring posts for a keyword.

LinkedIn itself is never contacted. New results come from the Tavily web search
API, which indexes public LinkedIn pages. Saved posts are searched offline.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import requests

from matcher.job_sources import iran_place
from matcher.post_offers import (
    PERSIAN_RE,
    PUBLIC_POSTS,
    TAVILY_SEARCH_URL,
    adapt_web_result,
    is_job_offer,
    linkedin_post_search_url,
    merge_posts,
    offer_text,
    published_day,
    strip_tags,
)
from matcher.scorer import contains_term, find_email, fold_title, home_country, linkedin_search_url, matches_regions

TIME_RANGES = ("day", "week", "month", "year")
JOB_PATH_RE = re.compile(r"^/jobs/view/[^/?#]+")
JOB_ID_RE = re.compile(r"(\d{6,})/?$")
HIRING_TITLE_RE = re.compile(r"^(?P<company>.+?) hiring (?P<title>.+?)(?: in (?P<location>.+))?$", re.I)
AT_TITLE_RE = re.compile(r"^(?P<title>.+?) at (?P<company>.+?)(?:\s+[—–]\s+(?P<location>.+))?$")
LINKEDIN_SUFFIX_RE = re.compile(r"(?:\s*[|\-–—]\s*(?:LinkedIn|Jobs))+\s*$", re.I)
SLUG_COMPANY_RE = re.compile(r"/jobs/view/[^/]*?-at-([a-z0-9-]+?)-\d{6,}$")
# LinkedIn has almost no job listings for Iran, so Iran searches look for remote roles.
REMOTE_COUNTRIES = {"Iran"}


def search_linkedin(
    keyword: str,
    location: str = "",
    since: str = "month",
    api_key: str = "",
    saved_posts: list[dict] | None = None,
    offline: bool = False,
) -> dict:
    keyword = " ".join(str(keyword or "").split())
    location = " ".join(str(location or "").split())
    if not keyword:
        raise ValueError("Give a keyword to search for.")
    if since not in TIME_RANGES:
        raise ValueError(f"since must be one of: {', '.join(TIME_RANGES)}.")
    country = home_country({"location": location})
    key = (api_key or os.environ.get("TAVILY_API_KEY", "")).strip()
    reports = []
    jobs: list[dict] = []
    web_posts: list[dict] = []
    if key and not offline:
        jobs, report = search_web_jobs(keyword, jobs_location(location, country), since, key)
        reports.append(report)
        web_posts, report = search_web_posts(keyword, location, country, since, key)
        reports.append(report)
    elif not offline:
        reports.append(
            {"name": "Web search", "ok": False, "count": 0, "error": "Set TAVILY_API_KEY to search for new jobs and posts."}
        )
    pool = merge_posts(web_posts, merge_posts(saved_posts or [], PUBLIC_POSTS, limit=5000), limit=5000)
    posts = [post for post in pool if is_post_match(post, keyword) and in_location(post, location, country)]
    reports.append({"name": "Saved posts", "ok": True, "count": len(posts), "error": ""})
    jobs.sort(key=lambda item: item.get("published") or "", reverse=True)
    posts.sort(key=lambda item: item.get("published") or "", reverse=True)
    return {
        "keyword": keyword,
        "location": location,
        "jobs": jobs,
        "posts": posts,
        "reports": reports,
        "links": {
            "jobs": linkedin_search_url(keyword, location, easy_apply=False),
            "posts": linkedin_post_search_url(post_query(keyword, location, country)),
        },
    }


def fetch_linkedin_jobs(profile: dict, since: str = "month") -> tuple[list[dict], dict]:
    """Find public LinkedIn job listings for the CV roles via search_web_jobs."""
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        return [], {"name": "LinkedIn jobs", "ok": False, "count": 0, "error": "Set TAVILY_API_KEY to search LinkedIn jobs."}
    titles = [str(title).strip() for title in (profile.get("target_titles") or []) if str(title).strip()][:2]
    if not titles:
        return [], {"name": "LinkedIn jobs", "ok": True, "count": 0, "error": ""}
    where = jobs_location(str(profile.get("location") or "").strip(), home_country(profile))
    found: list[dict] = []
    errors: list[str] = []
    for title in titles:
        jobs, report = search_web_jobs(title, where, since, key)
        if not report["ok"] and report.get("error"):
            errors.append(report["error"])
        found.extend(jobs)
    found = merge_jobs(found, [])
    if errors and not found:
        return [], {"name": "LinkedIn jobs", "ok": False, "count": 0, "error": errors[0]}
    return found, {"name": "LinkedIn jobs", "ok": True, "count": len(found), "error": ""}


def fetch_jobs_feed(url: str) -> tuple[list[dict], dict]:
    """Download LinkedIn jobs that the scheduled GitHub job already found."""
    try:
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return [], {"name": "LinkedIn jobs", "ok": False, "count": 0, "error": short_error(exc)}
    items = payload.get("jobs") if isinstance(payload, dict) else payload
    jobs = merge_jobs([job for job in (clean_job(item) for item in items or []) if job], [])
    return jobs, {"name": "LinkedIn jobs", "ok": True, "count": len(jobs), "error": ""}


def clean_job(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    url = job_url(str(item.get("url") or ""))
    title = strip_tags(item.get("title"))[:140]
    if not url or not title:
        return None
    snippet = strip_tags(item.get("snippet"))[:600]
    email = strip_tags(item.get("apply_email"))
    return {
        "title": title,
        "company": strip_tags(item.get("company"))[:140] or "LinkedIn job",
        "location": strip_tags(item.get("location"))[:80],
        "url": url,
        "published": published_day(item.get("published")),
        "snippet": snippet,
        "apply_email": email if email and find_email(email) == email else find_email(snippet),
        "source": "LinkedIn job",
    }


def merge_jobs(first: list[dict], second: list[dict], limit: int = 300) -> list[dict]:
    seen: set[str] = set()
    merged = []
    for job in [*first, *second]:
        if not isinstance(job, dict):
            continue
        url = str(job.get("url") or "")
        match = JOB_ID_RE.search(url)
        key = match.group(1) if match else url.split("?")[0].rstrip("/").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(job)
    return merged[:limit]


def jobs_location(location: str, country: str) -> str:
    return "remote" if country in REMOTE_COUNTRIES else location


def search_web_jobs(keyword: str, location: str, since: str, key: str) -> tuple[list[dict], dict]:
    name = "LinkedIn jobs (remote)" if location == "remote" else "LinkedIn jobs"
    query = " ".join(part for part in (keyword, location, "jobs") if part)
    try:
        results = tavily_search(query, "linkedin.com/jobs/view", since, key)
    except Exception as exc:
        return [], {"name": name, "ok": False, "count": 0, "error": short_error(exc)}
    seen: set[str] = set()
    jobs = []
    for item in results:
        job = adapt_job_result(item)
        if not job or not matches_keyword(f"{job['title']} {job['company']} {job['snippet']}", keyword):
            continue
        match = JOB_ID_RE.search(job["url"])
        dedupe = match.group(1) if match else job["url"].lower()
        if dedupe in seen:
            continue
        seen.add(dedupe)
        jobs.append(job)
    return jobs, {"name": name, "ok": True, "count": len(jobs), "error": ""}


def as_board_job(job: dict) -> dict:
    location = str(job.get("location") or "")
    remote = any(word in location.lower() for word in ("remote", "worldwide", "anywhere", "global"))
    return {
        "source": "LinkedIn job",
        "title": job.get("title") or "",
        "company": job.get("company") or "LinkedIn job",
        "location": location,
        "remote": remote,
        "url": job.get("url") or "",
        "description": job.get("snippet") or "",
        "tags": ["LinkedIn"],
        "published": job.get("published") or "",
        "salary": "",
    }


def search_web_posts(keyword: str, location: str, country: str, since: str, key: str) -> tuple[list[dict], dict]:
    try:
        results = tavily_search(post_query(keyword, location, country), "linkedin.com/posts", since, key)
    except Exception as exc:
        return [], {"name": "LinkedIn posts", "ok": False, "count": 0, "error": short_error(exc)}
    posts = [post for post in (adapt_web_result(item, country or location) for item in results) if post]
    posts = merge_posts(posts, [])
    return posts, {"name": "LinkedIn posts", "ok": True, "count": len(posts), "error": ""}


def post_query(keyword: str, location: str, country: str) -> str:
    if country == "Iran" or PERSIAN_RE.search(keyword):
        return f"استخدام {keyword}"
    return " ".join(part for part in ("hiring", keyword, location) if part)


def tavily_search(query: str, domain: str, since: str, key: str) -> list[dict]:
    response = requests.post(
        TAVILY_SEARCH_URL,
        json={
            "query": query,
            "search_depth": "basic",
            "max_results": 20,
            "time_range": since,
            "include_domains": [domain],
            "include_published_date": True,
        },
        headers={"Authorization": f"Bearer {key}"},
        timeout=20,
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    return [item for item in results if isinstance(item, dict)]


def adapt_job_result(item: dict) -> dict | None:
    url = job_url(str(item.get("url") or ""))
    if not url:
        return None
    raw_title = LINKEDIN_SUFFIX_RE.sub("", strip_tags(item.get("title"))).strip()
    if not raw_title:
        return None
    snippet = strip_tags(item.get("content"))[:600]
    company = ""
    location = ""
    match = HIRING_TITLE_RE.match(raw_title) or AT_TITLE_RE.match(raw_title)
    if match:
        title = match.group("title")
        company = match.group("company")
        location = match.group("location") or ""
    else:
        parts = [part.strip() for part in re.split(r"\s+[-–—|]\s+", raw_title) if part.strip()]
        from_url = slug_company(url)
        if not from_url:
            title, company = parts[0], (parts[1] if len(parts) > 1 else "")
        elif len(parts) > 1 and squash(parts[-1]) == squash(from_url):
            title, company = " - ".join(parts[:-1]), parts[-1]
        else:
            title, company = " - ".join(parts), from_url
    title, company, location = (trim_cut(value) for value in (title, company, location))
    company = company or slug_company(url)
    if not location:
        text = f"{raw_title} {snippet}"
        if PERSIAN_RE.search(text) or matches_regions(text.lower(), ["Iran"]):
            location = iran_place(text)
        elif re.search(r"\bremote\b", text, re.I):
            location = "Remote"
    return {
        "title": title[:140],
        "company": company[:140] or "LinkedIn job",
        "location": location[:80],
        "url": url,
        "published": published_day(item.get("published_date")),
        "snippet": snippet,
        "apply_email": find_email(snippet),
        "source": "LinkedIn job",
    }


def trim_cut(value: str) -> str:
    """Drop the '...' that search engines add to shortened titles."""
    return re.sub(r"\s*(?:\.{3}|…)\s*$", "", value or "").strip(" -–—|")


def squash(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def slug_company(url: str) -> str:
    match = SLUG_COMPANY_RE.search(url)
    if not match:
        return ""
    return " ".join(word.capitalize() for word in match.group(1).split("-") if word)


def job_url(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        return ""
    match = JOB_PATH_RE.match(parsed.path)
    if not match:
        return ""
    return "https://www.linkedin.com" + match.group(0)


def is_post_match(post: dict, keyword: str) -> bool:
    text = offer_text(post)
    return is_job_offer(text, [keyword]) and matches_keyword(text, keyword)


def matches_keyword(text: str, keyword: str) -> bool:
    """True when every word of the keyword appears in the text."""
    folded = fold_title(text)
    plain = text.replace("\u200c", " ")
    terms = keyword.split() if PERSIAN_RE.search(keyword) else fold_title(keyword).split()
    for term in terms:
        if PERSIAN_RE.search(term):
            if term not in plain and term not in text:
                return False
        elif not (contains_term(text, term) or contains_term(folded, term)):
            return False
    return True


def in_location(post: dict, location: str, country: str) -> bool:
    if not location:
        return True
    place = str(post.get("location") or "").lower()
    if not place:
        return True
    tokens = [part.strip().lower() for part in location.split(",") if len(part.strip()) >= 2]
    if any(token in place for token in tokens):
        return True
    return bool(country) and matches_regions(place, [country])


def short_error(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    return (text[0] if text else exc.__class__.__name__)[:180]
