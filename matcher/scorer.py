"""Score jobs against a CV profile and write a plain application letter."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlencode

GENERIC_TITLE_WORDS = {
    "senior", "junior", "lead", "principal", "staff", "head", "of", "and", "the",
    "a", "an", "i", "ii", "iii", "iv", "with", "for", "in", "at",
}

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
SKIP_EMAIL = ("noreply", "no-reply", "example.com", "email.com", "sentry.io")


def score_and_rank(profile: dict, jobs: list[dict], easy_apply: bool = True) -> list[dict]:
    ranked = []
    for job in jobs:
        scored = score_job(profile, job)
        if scored is None or scored["score"] < 15:
            continue
        letter = cover_letter(profile, job, scored["matched_skills"])
        record = {
            "id": job_id(job),
            "title": job["title"],
            "company": job["company"],
            "location": job.get("location") or "",
            "remote": bool(job.get("remote")),
            "url": job.get("url") or "",
            "source": job.get("source") or "",
            "published": job.get("published") or "",
            "salary": job.get("salary") or "",
            "snippet": snippet(job.get("description") or ""),
            "score": scored["score"],
            "fit_label": fit_label(scored["score"]),
            "matched_skills": scored["matched_skills"][:8],
            "reason": scored["reason"],
            "priority": scored["priority"],
            "cover_letter": letter,
            "apply_email": find_email(job.get("description") or ""),
            "linkedin_search_url": linkedin_search_url(
                job["title"],
                linkedin_location(profile, job),
                easy_apply=easy_apply,
                remote_only=bool(profile.get("remote_only")),
            ),
        }
        ranked.append(record)
    ranked.sort(key=lambda item: (-item["priority"], -item["score"], item["title"]))
    return ranked[:40]


def score_job(profile: dict, job: dict) -> dict | None:
    points, keep = location_points(profile, job)
    if not keep:
        return None

    haystack = " ".join(
        [
            job.get("title") or "",
            job.get("description") or "",
            " ".join(job.get("tags") or []),
        ]
    )
    skills = [skill for skill in profile.get("skills") or [] if skill]
    matched = [skill for skill in skills if contains_term(haystack, skill)]
    denom = min(max(len(skills), 1), 10)
    skill_points = round(min(len(matched), denom) / denom * 55)
    role_points = title_points(profile.get("target_titles") or [], job.get("title") or "")
    if other_stack(job.get("title") or "", skills) or role_points < 22:
        return None
    total = min(100, skill_points + role_points + points)
    regions = [str(item).strip() for item in (profile.get("target_regions") or []) if str(item).strip()]
    home = home_country(profile)
    job_loc = (job.get("location") or "").lower()
    priority = 1 if home and matches_regions(job_loc, [home]) else 0

    reasons = []
    if priority:
        reasons.append(f"This role is in {home}, so it is listed first.")
    if role_points >= 30:
        reasons.append("The job title lines up with a role you want.")
    else:
        reasons.append("The main words from your target role are in this title.")
    if matched:
        reasons.append("Skills in common: " + ", ".join(matched[:8]) + ".")
    if regions and not priority:
        reasons.append("Hiring region: " + ", ".join(regions) + ".")

    return {
        "score": total,
        "matched_skills": matched,
        "reason": " ".join(reasons),
        "priority": priority,
    }


def title_points(titles: list[str], job_title: str) -> int:
    folded = fold_title(job_title)
    best = 0
    job_words = {same_role(word) for word in significant_words(folded)}
    for target in titles:
        folded_target = fold_title(target)
        if contains_term(folded, target) or contains_term(folded, folded_target):
            best = max(best, 30)
            continue
        # Fold first so Persian roles like "توسعه‌دهنده فرانت‌اند" can match English jobs.
        words = [same_role(word) for word in significant_words(folded_target)]
        if words and all(word in job_words or contains_term(folded, word) for word in words):
            best = max(best, 22)
    return best


def fold_title(title: str) -> str:
    text = title.replace("\u200c", " ").replace("&zwnj;", " ")
    folded = text.lower().replace("front-end", "frontend").replace("front end", "frontend")
    folded = folded.replace("full-stack", "full stack").replace("fullstack", "full stack")
    folded = folded.replace("back-end", "backend").replace("back end", "backend")
    if "فرانت" in text:
        folded += " frontend developer"
    if "توسعه دهنده" in text.replace("\u200c", " ") or "برنامه نویس" in text.replace("\u200c", " "):
        folded += " developer"
    if ("بک" in text and "اند" in text) or "بکند" in text:
        folded += " backend developer"
    if "فول" in text:
        folded += " full stack developer"
    return folded


def same_role(word: str) -> str:
    if word in {"developer", "engineer", "programmer"}:
        return "developer"
    return word


OTHER_STACKS = (
    ".net", "c#", "rails", "ruby", "java", "php", "shopify", "wordpress", "angular",
    "vue", "django", "laravel", "ios", "android", "kotlin", "swift", "golang",
)


def other_stack(job_title: str, skills: list[str]) -> bool:
    owned = {skill.lower() for skill in skills}
    for stack in OTHER_STACKS:
        if stack in owned or stack.lstrip(".") in owned:
            continue
        if contains_term(job_title, stack):
            return True
    return False


def significant_words(title: str) -> list[str]:
    words = re.findall(r"[a-z0-9+#]+", title.lower())
    return [word for word in words if word not in GENERIC_TITLE_WORDS and len(word) > 2]


REGION_PLACES = {
    "germany": ("germany", "deutschland", "berlin", "munich", "hamburg", "frankfurt", "cologne", "stuttgart", "leipzig"),
    "austria": ("austria", "vienna", "wien", "salzburg", "graz", "linz", "innsbruck"),
    "europe": (
        "europe", "european", "eu", "emea", "germany", "deutschland", "austria", "netherlands",
        "amsterdam", "france", "paris", "belgium", "brussels", "switzerland", "zurich", "sweden",
        "stockholm", "norway", "oslo", "denmark", "copenhagen", "finland", "helsinki", "ireland",
        "dublin", "spain", "madrid", "barcelona", "italy", "milan", "portugal", "lisbon", "poland",
        "warsaw", "czech", "prague", "luxembourg", "united kingdom", "london", "berlin", "munich",
        "hamburg", "vienna",
    ),
    "united states": (
        "united states", "usa", "u.s.", "america", "americas", "north america", "new york",
        "california", "seattle", "austin", "boston", "chicago", "san francisco", "los angeles", "texas",
    ),
    "canada": ("canada", "toronto", "vancouver", "montreal", "ottawa"),
    "american countries": ("united states", "usa", "canada", "north america", "america", "americas"),
    "iran": ("iran", "tehran", "isfahan", "esfahan", "mashhad", "shiraz", "tabriz", "karaj", "qom", "ahvaz", "yazd", "rasht"),
    "united kingdom": ("united kingdom", "uk", "london", "britain", "england", "manchester"),
    "france": ("france", "paris", "lyon"),
    "netherlands": ("netherlands", "amsterdam", "holland"),
    "belgium": ("belgium", "brussels"),
    "switzerland": ("switzerland", "zurich", "geneva"),
    "sweden": ("sweden", "stockholm"),
    "norway": ("norway", "oslo"),
    "denmark": ("denmark", "copenhagen"),
    "finland": ("finland", "helsinki"),
    "ireland": ("ireland", "dublin"),
    "spain": ("spain", "madrid", "barcelona"),
    "italy": ("italy", "milan", "rome"),
    "portugal": ("portugal", "lisbon"),
    "poland": ("poland", "warsaw"),
    "turkey": ("turkey", "turkiye", "türkiye", "istanbul", "ankara"),
    "united arab emirates": ("united arab emirates", "uae", "dubai", "abu dhabi"),
}


COUNTRY_NAMES = (
    "United Arab Emirates",
    "United Kingdom",
    "United States",
    "Netherlands",
    "Switzerland",
    "Germany",
    "Austria",
    "Canada",
    "France",
    "Belgium",
    "Sweden",
    "Norway",
    "Denmark",
    "Finland",
    "Ireland",
    "Spain",
    "Italy",
    "Portugal",
    "Poland",
    "Turkey",
    "Iran",
    "Europe",
)


def location_points(profile: dict, job: dict) -> tuple[int, bool]:
    job_loc = (job.get("location") or "").strip().lower()
    remote = is_remote(job, job_loc)
    if profile.get("remote_only") and not remote:
        return 0, False
    regions = [str(item).strip() for item in (profile.get("target_regions") or []) if str(item).strip()]
    priority = home_priority(profile)
    if profile.get("all_countries"):
        if priority and matches_regions(job_loc, priority):
            return 15, True
        return 10, True
    if regions or priority:
        if priority and matches_regions(job_loc, priority):
            return 15, True
        if regions and matches_regions(job_loc, regions):
            return 12, True
        if not job_loc or any(word in job_loc for word in ("worldwide", "anywhere", "global", "work from home")):
            return 10, True
        if job_loc in {"remote", "remote job"}:
            return 10, True
        return 0, False
    user_loc = (profile.get("location") or "").strip().lower()
    if not user_loc:
        return (10 if remote else 0), True
    tokens = [part.strip() for part in user_loc.split(",") if len(part.strip()) >= 2]
    if any(token in job_loc for token in tokens):
        return 15, True
    if remote or not job_loc:
        return 8, True
    return 0, False


def home_country(profile: dict) -> str:
    home = (profile.get("location") or "").strip().lower()
    if not home:
        return ""
    for name in COUNTRY_NAMES:
        if name.lower() in home:
            return name
        places = REGION_PLACES.get(name.lower(), ())
        for place in places:
            if place in {"europe"}:
                continue
            if len(place) <= 3:
                if contains_term(home, place):
                    return name
            elif place in home:
                return name
    return ""


def home_priority(profile: dict) -> list[str]:
    country = home_country(profile)
    return [country] if country else []


def in_iran(job: dict) -> bool:
    return matches_regions((job.get("location") or "").lower(), ["Iran"])


def matches_regions(job_loc: str, regions: list[str]) -> bool:
    for region in regions:
        places = REGION_PLACES.get(region.lower(), (region.lower(),))
        for place in places:
            if len(place) <= 3:
                if contains_term(job_loc, place):
                    return True
            elif place in job_loc:
                return True
    return False


def is_remote(job: dict, job_loc: str) -> bool:
    if job.get("remote"):
        return True
    return any(word in job_loc for word in ("remote", "worldwide", "anywhere", "global", "work from home"))


def contains_term(text: str, term: str) -> bool:
    term = " ".join(str(term).lower().split())
    if not term:
        return False
    pattern = r"(?<!\w)" + re.escape(term).replace(r"\ ", r"\s+") + r"(?!\w)"
    return re.search(pattern, text, flags=re.I) is not None


def linkedin_location(profile: dict, job: dict) -> str:
    regions = [str(item).strip() for item in (profile.get("target_regions") or []) if str(item).strip()]
    priority = home_priority(profile)
    job_loc = (job.get("location") or "").strip()
    if job_loc and (matches_regions(job_loc.lower(), regions) or matches_regions(job_loc.lower(), priority)):
        return job_loc
    if regions or priority:
        return ""
    user_loc = (profile.get("location") or "").strip()
    if user_loc:
        return user_loc
    lowered = job_loc.lower()
    if not job_loc or any(word in lowered for word in ("remote", "world", "anywhere", "global")):
        return ""
    return job_loc


def linkedin_search_url(title: str, location: str, easy_apply: bool = True, remote_only: bool = False) -> str:
    params = {"keywords": title, "f_TPR": "r2592000"}
    if location:
        params["location"] = location
    if easy_apply:
        params["f_AL"] = "true"
    if remote_only:
        params["f_WT"] = "2"
    return "https://www.linkedin.com/jobs/search/?" + urlencode(params)


def cover_letter(profile: dict, job: dict, matched_skills: list[str]) -> str:
    name = profile.get("name") or "Applicant"
    title = job.get("title") or "the open role"
    company = job.get("company") or "your team"
    role = (profile.get("target_titles") or [""])[0].strip()
    skills = [skill for skill in matched_skills if skill]
    if not skills:
        skills = list(profile.get("skills") or [])[:5]
    opening = f"I am writing to apply for the {title} position at {company}."
    if role:
        opening += f" I am a {role}, and this opening matches the work I want to do next."
    else:
        opening += " This opening matches the work I want to do next."
    paragraphs = ["Dear Hiring Manager,", opening]
    if skills:
        listed = ", ".join(skills[:5])
        paragraphs.append(f"The parts of my experience most relevant to this role are {listed}.")
    summary = " ".join((profile.get("summary") or "").split())
    if summary:
        paragraphs.append(summary if summary.endswith(".") else summary + ".")
    regions = [str(item).strip() for item in (profile.get("target_regions") or []) if str(item).strip()]
    home = (profile.get("location") or "").strip()
    home_name = home_country(profile)
    job_loc = (job.get("location") or "").lower()
    if in_iran(job):
        based = f"I am based in {home}. " if home else ""
        paragraphs.append(f"{based}I am available for this role in Iran.")
    elif home_name and matches_regions(job_loc, [home_name]):
        based = f"I am based in {home}. " if home else ""
        paragraphs.append(f"{based}I am available for this role in {home_name}.")
    elif regions or profile.get("all_countries"):
        where = "any country" if profile.get("all_countries") else ", ".join(regions)
        based = f"I am based in {home}. " if home else ""
        paragraphs.append(
            f"{based}I am ready to work remotely or relocate for this role in {where}."
        )
    paragraphs.append(
        "I have attached my CV. I would be glad to talk about how I can help the team. Thank you for your time."
    )
    closing = ["Best regards,", name]
    contact = " | ".join(item for item in (profile.get("email"), profile.get("phone")) if item)
    if contact:
        closing.append(contact)
    paragraphs.append("\n".join(closing))
    return "\n\n".join(paragraphs)


def find_email(text: str) -> str:
    for match in EMAIL_RE.findall(text or ""):
        lowered = match.lower()
        if any(blocked in lowered for blocked in SKIP_EMAIL):
            continue
        return match
    return ""


def snippet(text: str, limit: int = 320) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit].rsplit(" ", 1)[0]
    return cut + "..."


def fit_label(score: int) -> str:
    if score >= 75:
        return "Strong match"
    if score >= 50:
        return "Good match"
    return "Possible match"


def job_id(job: dict) -> str:
    raw = "|".join(
        [
            job.get("source") or "",
            job.get("url") or "",
            job.get("title") or "",
            job.get("company") or "",
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
