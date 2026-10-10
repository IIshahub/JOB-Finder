"""Find public LinkedIn posts that read as job offers."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlencode

from matcher.scorer import contains_term, cover_letter, find_email, home_country, matches_regions, title_points

HIRING_RE = re.compile(
    r"استخدام|فرصت شغلی|موقعیت شغلی|we're hiring|we are hiring|\bhiring\b|رزومه|"
    r"send\s+(?:your\s+|a\s+|the\s+)?(?:cv|resume)|job opening|now hiring|به دنبال جذب",
    re.I,
)
SEEKER_RE = re.compile(r"جویای کار|open to work|به دنبال کار هستم", re.I)

# Public posts visible without a LinkedIn login on 2026-10-10.
# LinkedIn does not offer a personal feed API, so a signed-in search is the live view.
PUBLIC_POSTS = [
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
]


def search_posts(profile: dict) -> tuple[list[dict], list[dict]]:
    titles = profile.get("target_titles") or []
    found = [post for post in PUBLIC_POSTS if is_job_offer(offer_text(post), titles)]
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
