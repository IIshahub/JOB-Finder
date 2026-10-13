"""Find public LinkedIn posts that read as job offers."""

from __future__ import annotations

import hashlib
import os
import re
import time
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import unquote, urlencode, urlparse

import requests

from matcher.job_sources import iran_place, iso_date
from matcher.scorer import contains_term, cover_letter, find_email, home_country, matches_regions, title_points

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
# Tavily's free plan allows 1,000 searches a month, shared by every visitor.
SEARCH_COOLDOWN = 6 * 3600
POST_PATH_RE = re.compile(r"^/posts/[^/?#]+")
PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")

HIRING_RE = re.compile(
    r"استخدام|فرصت شغلی|موقعیت شغلی|we're hiring|we are hiring|\bhiring\b|رزومه|"
    r"send\s+(?:your\s+|a\s+|the\s+)?(?:cv|resume)|job opening|now hiring|به دنبال جذب",
    re.I,
)
SEEKER_RE = re.compile(r"جویای کار|open to work|به دنبال کار هستم", re.I)

# Public posts visible without a LinkedIn login on 2026-10-13.
# LinkedIn does not offer a personal feed API, so a signed-in search is the live view.
PUBLIC_POSTS = [
    {
        "title": "استخدام کارآموز فرانت اند، حضوری، تهران",
        "company": "Fararo",
        "location": "Tehran, Iran",
        "url": "https://www.linkedin.com/posts/fara-ro_%D8%A2%DA%AF%D9%87%DB%8C%D8%A7%D8%B3%D8%AA%D8%AE%D8%AF%D8%A7%D9%85%DB%8C-activity-7512122623011516416-3Nix",
        "published": "2026-10-03",
        "snippet": "On-site frontend intern in Tehran for people who have worked with React or Next.js. Send a CV to mail@fararo.org.",
        "apply_email": "mail@fararo.org",
    },
    {
        "title": "استخدام توسعه دهنده فرانت اند میدلول",
        "company": "Sepid System",
        "location": "Tehran, Iran",
        "url": "https://www.linkedin.com/posts/sepid-system_activity-7510265925338578944-3qJB",
        "published": "2026-09-28",
        "snippet": "Mid-level frontend developer in Tehran, on-site. React, TypeScript, HTML, CSS, and REST. Send a CV to cto@sepidsystem.com.",
        "apply_email": "cto@sepidsystem.com",
    },
    {
        "title": "فرصت شغلی: Frontend React, Next.js, TypeScript",
        "company": "Viuna ICT",
        "location": "Iran",
        "url": "https://www.linkedin.com/posts/viuna-ict_activity-7507396642191392768-BgTb",
        "published": "2026-09-20",
        "snippet": "Frontend developer for React, Next.js, and TypeScript, including the App Router. At least two years of experience.",
        "apply_email": "",
    },
    {
        "title": "Senior Front-End Developer (React)",
        "company": "Sanaap",
        "location": "Tehran, Iran",
        "url": "https://www.linkedin.com/posts/sanaap_%D8%A7%D8%B3%D8%AA%D8%AE%D8%AF%D8%A7%D9%85-seniorfrontend-%D8%B3%D9%86%D8%A7%D9%BE-activity-7498362726239346689-rzEj",
        "published": "2026-08-26",
        "snippet": "Senior React frontend developer, on-site in Yousefabad, Tehran. Send a CV to hr.sanaap@gmail.com.",
        "apply_email": "hr.sanaap@gmail.com",
    },
    {
        "title": "استخدام Frontend Developer، تمام وقت، حضوری",
        "company": "Helix Game",
        "location": "Tehran, Iran",
        "url": "https://www.linkedin.com/posts/helixserver_activity-7495538060328144897-R0fm",
        "published": "2026-08-18",
        "snippet": "On-site frontend role in Tehran. React, Next.js, TypeScript, CSS, REST, Docker, and Git. Pay listed around 45 to 55 million toman.",
        "apply_email": "",
    },
    {
        "title": "برنامه نویس فرانت اند، تمام وقت، تهران",
        "company": "Posted by Ehsan Yari",
        "location": "Tehran, Iran",
        "url": "https://www.linkedin.com/posts/ehsan-yari-bb3b92228_%D8%A7%D8%B3%D8%AA%D8%AE%D8%AF%D8%A7%D9%85-%D9%81%D8%B1%D8%A7%D9%86%D8%AA%D8%A7%D9%86%D8%AF-react-activity-7472180733319614464-9q77",
        "published": "2026-06-15",
        "snippet": "Full-time Tehran frontend role. React, TypeScript, MUI, and at least two years of experience. Send the CV in the post thread.",
        "apply_email": "",
    },
    {
        "title": "Senior Front-End Developer",
        "company": "Dade Amay Datis",
        "location": "Tehran, Iran",
        "url": "https://www.linkedin.com/posts/javadyosuefi_senior-front-end-developer-%D9%85%D9%88%D9%82%D8%B9%DB%8C%D8%AA-%D8%B4%D8%BA%D9%84%DB%8C-activity-7471813392245178368-ZlU9",
        "published": "2026-06-14",
        "snippet": "Senior React and Next.js role in Mirdamad, Tehran. TypeScript, Tailwind, and PWA. Send a CV to Javadyousefi9000@gmail.com.",
        "apply_email": "Javadyousefi9000@gmail.com",
    },
    {
        "title": "استخدام Senior Front-end Developer",
        "company": "Rokham",
        "location": "Mashhad, Iran",
        "url": "https://www.linkedin.com/posts/mostafa-kermani-pmp-%C2%AE-84390879_%D8%A7%D8%B3%D8%AA%D8%AE%D8%AF%D8%A7%D9%85-senior-front-end-developer-activity-7503327401154760704-Irpm",
        "published": "2026-09-09",
        "snippet": "Senior React, Next.js, and TypeScript role in Mashhad, remote possible, project-based or part-time. Contact on Telegram at @kermani_rkm.",
        "apply_email": "",
    },
    {
        "title": "استخدام Frontend Developer، LendTech، جردن",
        "company": "Posted by Alireza Zarezade",
        "location": "Tehran, Iran",
        "url": "https://www.linkedin.com/posts/alireza-zarezade_hiring-frontend-frontenddeveloper-activity-7496934042739724288-xqif",
        "published": "2026-08-22",
        "snippet": "Full-time on-site frontend role at a LendTech company in Jordan, Tehran. Two to three years with React, Next.js App Router, and TypeScript. Send a CV to a.r.zarezade@gmail.com with the subject Frontend Developer.",
        "apply_email": "a.r.zarezade@gmail.com",
    },
    {
        "title": "استخدام Frontend Developer (React / Next.js)",
        "company": "Posted by Mahla Motaghi",
        "location": "Tehran, Iran",
        "url": "https://www.linkedin.com/posts/mahlamotaghi72_%D8%A7%D8%B3%D8%AA%D8%AE%D8%AF%D8%A7%D9%85-frontend-developer-react-nextjs-activity-7492863393628966912-DD1r",
        "published": "",
        "snippet": "Full-time on-site frontend role near Argentina Square, Tehran. React, Next.js, TypeScript, TanStack Query, Zustand, and Tailwind. Send the CV by LinkedIn message.",
        "apply_email": "",
    },
    {
        "title": "Frontend Developer (React / Next.js)",
        "company": "Loopex",
        "location": "Tehran, Iran",
        "url": "https://www.linkedin.com/posts/loopexchange_frontend-developer-react-nextjs-loopex-activity-7485779674409791488-lwZW",
        "published": "2026-07-22",
        "snippet": "Frontend role at a Tehran crypto exchange. At least three years with React and Next.js. Pay listed at 75 to 95 million per month. Send a CV to hiring@loopex.ir.",
        "apply_email": "hiring@loopex.ir",
    },
]


def search_posts(profile: dict, extra_posts: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    titles = profile.get("target_titles") or []
    pool = merge_posts(extra_posts or [], PUBLIC_POSTS)
    found = [post for post in pool if is_job_offer(offer_text(post), titles)]
    report = {"name": "LinkedIn posts", "ok": True, "count": len(found), "error": ""}
    ranked = [decorate_post(profile, post) for post in found]
    ranked.sort(key=lambda item: (item["priority"], item.get("published") or ""), reverse=True)
    return ranked[:20], [report]


def offer_text(post: dict) -> str:
    return " ".join(str(post.get(key) or "") for key in ("title", "snippet", "location"))


def is_job_offer(text: str, titles: list[str]) -> bool:
    if not text or not HIRING_RE.search(text):
        return False
    if SEEKER_RE.search(text) and not re.search(r"استخدام|فرصت شغلی|موقعیت شغلی|\bhiring\b", text, re.I):
        return False
    if titles and title_points(titles, text) >= 22:
        return True
    lowered = text.lower()
    return any(token in lowered or token in text for token in ("frontend", "front-end", "react", "فرانت", "next.js", "nextjs"))


def decorate_post(profile: dict, post: dict) -> dict:
    title = str(post.get("title") or "LinkedIn job offer").strip()
    company = str(post.get("company") or "LinkedIn post").strip()
    location = str(post.get("location") or "").strip()
    snippet = str(post.get("snippet") or "").strip()
    url = str(post.get("url") or "").split("?")[0]
    email = str(post.get("apply_email") or "").strip() or find_email(snippet)
    skills = [skill for skill in profile.get("skills") or [] if contains_term(f"{title} {snippet}", skill)]
    job = {
        "title": title,
        "company": company,
        "location": location,
        "description": snippet,
    }
    record = {
        "id": hashlib.sha1(url.encode("utf-8")).hexdigest()[:12],
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "published": str(post.get("published") or ""),
        "snippet": snippet,
        "apply_email": email,
        "source": "LinkedIn post",
        "priority": 1 if matches_regions(location.lower(), [home_country(profile) or "Iran"]) else 0,
        "reason": "This LinkedIn post is a job offer" + (f" in {location}." if location else "."),
        "matched_skills": skills[:8],
        "cover_letter": cover_letter(profile, job, skills),
    }
    return record


def post_search_links(profile: dict) -> list[dict]:
    role = (profile.get("target_titles") or ["Frontend Developer"])[0]
    regions = [str(item).strip() for item in (profile.get("target_regions") or []) if str(item).strip()]
    home = home_country(profile)
    if profile.get("all_countries") and not regions:
        regions = [home or "Iran"]
    if not regions:
        regions = [home or "Iran"]
    if home:
        regions = [home] + [region for region in regions if region.lower() != home.lower()]
    links = []
    for region in regions:
        if region.lower() == "iran":
            keyword = f"استخدام {role} تهران"
        else:
            keyword = f"hiring {role} {region}"
        links.append({"label": f"{role} posts · {region}", "url": linkedin_post_search_url(keyword)})
    return links


def linkedin_post_search_url(keywords: str) -> str:
    return "https://www.linkedin.com/search/results/content/?" + urlencode(
        {"keywords": keywords, "origin": "GLOBAL_SEARCH_HEADER", "sortBy": '"date_posted"'}
    )


def fetch_web_posts(profile: dict, searched_at: dict | None = None) -> tuple[list[dict], dict, dict]:
    """Ask a web search engine for public LinkedIn posts. LinkedIn itself is never contacted.

    `searched_at` maps each query to the time it last ran; queries newer than
    SEARCH_COOLDOWN are skipped. The updated map is returned for saving.
    """
    now = time.time()
    searched = {
        query: stamp
        for query, stamp in (searched_at or {}).items()
        if isinstance(stamp, (int, float)) and now - stamp < SEARCH_COOLDOWN
    }
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        report = {"name": "Web search", "ok": False, "count": 0, "error": "Set TAVILY_API_KEY to look for new posts."}
        return [], report, searched
    found: list[dict] = []
    try:
        for query, region in web_queries(profile):
            cache_key = query.lower()
            if cache_key in searched:
                continue
            response = requests.post(
                TAVILY_SEARCH_URL,
                json={
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 20,
                    "time_range": "month",
                    "include_domains": ["linkedin.com/posts"],
                    "include_published_date": True,
                },
                headers={"Authorization": f"Bearer {key}"},
                timeout=20,
            )
            response.raise_for_status()
            searched[cache_key] = now
            for item in response.json().get("results") or []:
                post = adapt_web_result(item, region)
                if post:
                    found.append(post)
    except Exception as exc:
        found = merge_posts(found, [])
        message = (str(exc).strip().splitlines() or [exc.__class__.__name__])[0][:180]
        return found, {"name": "Web search", "ok": False, "count": len(found), "error": message}, searched
    found = merge_posts(found, [])
    return found, {"name": "Web search", "ok": True, "count": len(found), "error": ""}, searched


def web_queries(profile: dict) -> list[tuple[str, str]]:
    roles = (profile.get("target_titles") or ["Frontend Developer"])[:2]
    home = home_country(profile) or "Iran"
    queries = []
    for role in roles:
        if home.lower() == "iran":
            queries.append((f"استخدام {role}", home))
        else:
            queries.append((f"hiring {role} {home}", home))
    return queries


def adapt_web_result(item: dict, region: str) -> dict | None:
    if not isinstance(item, dict):
        return None
    url = post_url(str(item.get("url") or ""))
    if not url:
        return None
    title = strip_tags(item.get("title"))
    title = re.sub(r"\s*[|\-–]\s*LinkedIn\s*$", "", title).strip()
    snippet = strip_tags(item.get("content"))[:600]
    if not title:
        return None
    text = f"{title} {snippet}"
    if region.lower() == "iran" or PERSIAN_RE.search(text):
        location = iran_place(text)
    else:
        location = region
    return {
        "title": title[:140],
        "company": post_author(url),
        "location": location,
        "url": url,
        "published": published_day(item.get("published_date")),
        "snippet": snippet,
        "apply_email": find_email(snippet),
    }


def published_day(value) -> str:
    day = iso_date(value)
    if day or not value:
        return day
    try:
        return parsedate_to_datetime(str(value)).date().isoformat()
    except (TypeError, ValueError):
        return ""


def post_url(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        return ""
    match = POST_PATH_RE.match(parsed.path)
    if not match:
        return ""
    return "https://www.linkedin.com" + match.group(0)


def post_author(url: str) -> str:
    slug = unquote(url.rsplit("/posts/", 1)[-1]).split("_", 1)[0]
    words = [word for word in slug.split("-") if word and not re.fullmatch(r"[0-9a-f]{6,}", word)]
    name = " ".join(word.capitalize() for word in words if not PERSIAN_RE.search(word))
    return f"Posted by {name}" if name else "LinkedIn post"


def strip_tags(value) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def merge_posts(first: list[dict], second: list[dict], limit: int = 120) -> list[dict]:
    seen: set[str] = set()
    merged = []
    for post in [*first, *second]:
        if not isinstance(post, dict):
            continue
        key = str(post.get("url") or "").split("?")[0].rstrip("/").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(post)
    return merged[:limit]


def fetch_feed_posts(url: str) -> tuple[list[dict], dict]:
    """Download posts that a scheduled job outside this server already found."""
    try:
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        message = (str(exc).strip().splitlines() or [exc.__class__.__name__])[0][:180]
        return [], {"name": "Post feed", "ok": False, "count": 0, "error": message}
    items = payload.get("posts") if isinstance(payload, dict) else payload
    posts = [post for post in (clean_post(item) for item in items or []) if post]
    posts = merge_posts(posts, [])
    return posts, {"name": "Post feed", "ok": True, "count": len(posts), "error": ""}


def clean_post(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    url = post_url(str(item.get("url") or ""))
    title = strip_tags(item.get("title"))[:140]
    if not url or not title:
        return None
    snippet = strip_tags(item.get("snippet"))[:600]
    email = strip_tags(item.get("apply_email"))
    return {
        "title": title,
        "company": strip_tags(item.get("company"))[:140] or post_author(url),
        "location": strip_tags(item.get("location"))[:80],
        "url": url,
        "published": iso_date(item.get("published")),
        "snippet": snippet,
        "apply_email": email if email and find_email(email) == email else find_email(snippet),
    }
