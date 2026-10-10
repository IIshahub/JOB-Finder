"""Fetch open roles from job boards that publish a public feed."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser

import requests

HEADERS = {
    "User-Agent": "cv-job-matcher/1.0 (personal job search)",
    "Accept": "application/json",
}

SOURCES = (
    ("Remotive", "https://remotive.com/api/remote-jobs"),
    ("Arbeitnow", "https://www.arbeitnow.com/api/job-board-api"),
    ("Remote OK", "https://remoteok.com/api"),
    ("Jobicy", "https://jobicy.com/api/v2/remote-jobs"),
)


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip = True
        if tag in {"p", "br", "li", "div", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = False

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(value: str) -> str:
    if not value:
        return ""
    parser = _HTMLText()
    parser.feed(str(value))
    parser.close()
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def iso_date(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        stamp = float(value)
        if stamp > 10_000_000_000:
            stamp = stamp / 1000
        try:
            return datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    text = str(value).strip()
    if text.isdigit():
        return iso_date(int(text))
    match = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else ""


def search_jobs(titles: list[str]) -> tuple[list[dict], list[dict]]:
    fetchers = (
        fetch_remotive,
        fetch_arbeitnow,
        fetch_remoteok,
        fetch_jobicy,
        fetch_jobinja,
        fetch_jobvision,
        fetch_quera,
        fetch_eestekhdam,
        fetch_irantalent,
        fetch_kardix,
    )
    jobs: list[dict] = []
    reports: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(fetchers)) as pool:
        futures = [pool.submit(fetcher, titles) for fetcher in fetchers]
        for future in futures:
            found, report = future.result()
            jobs.extend(found)
            reports.append(report)
    return dedupe_jobs(jobs), reports


def fetch_remotive(titles: list[str]) -> tuple[list[dict], dict]:
    try:
        found = []
        seen: set[str] = set()
        queries = titles[:2] or [""]
        for title in queries:
            response = requests.get(
                SOURCES[0][1],
                params={"search": title},
                headers=HEADERS,
                timeout=15,
            )
            response.raise_for_status()
            for item in (response.json().get("jobs") or [])[:30]:
                job = adapt_remotive(item)
                if job and job["url"] not in seen:
                    seen.add(job["url"])
                    found.append(job)
        return found, report("Remotive", found)
    except Exception as exc:
        return [], report("Remotive", error=short_error(exc))


def fetch_arbeitnow(titles: list[str]) -> tuple[list[dict], dict]:
    del titles
    try:
        response = requests.get(SOURCES[1][1], headers=HEADERS, timeout=15)
        response.raise_for_status()
        found = []
        for item in (response.json().get("data") or [])[:80]:
            job = adapt_arbeitnow(item)
            if job:
                found.append(job)
        return found, report("Arbeitnow", found)
    except Exception as exc:
        return [], report("Arbeitnow", error=short_error(exc))


def fetch_remoteok(titles: list[str]) -> tuple[list[dict], dict]:
    del titles
    try:
        response = requests.get(SOURCES[2][1], headers=HEADERS, timeout=15)
        response.raise_for_status()
        payload = response.json()
        found = []
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict) or not item.get("position"):
                    continue
                job = adapt_remoteok(item)
                if job:
                    found.append(job)
                if len(found) >= 80:
                    break
        return found, report("Remote OK", found)
    except Exception as exc:
        return [], report("Remote OK", error=short_error(exc))


def fetch_jobicy(titles: list[str]) -> tuple[list[dict], dict]:
    try:
        tag = role_tag(titles[0]) if titles else ""
        params = {"count": 50}
        if tag:
            params["tag"] = tag
        response = requests.get(SOURCES[3][1], params=params, headers=HEADERS, timeout=15)
        response.raise_for_status()
        found = []
        for item in (response.json().get("jobs") or [])[:50]:
            job = adapt_jobicy(item)
            if job:
                found.append(job)
        return found, report("Jobicy", found)
    except Exception as exc:
        return [], report("Jobicy", error=short_error(exc))


JOBINJA_CARD_RE = re.compile(
    r'class="c-jobListView__titleLink"[^>]*href="([^"]+)"[^>]*>\s*(.*?)\s*</a>'
    r'.*?c-icon--construction"></i>\s*<span>(.*?)</span>'
    r'.*?c-icon--place"></i>\s*<span>\s*(.*?)\s*</span>',
    re.S,
)


def fetch_jobinja(titles: list[str]) -> tuple[list[dict], dict]:
    try:
        found = []
        seen: set[str] = set()
        for keyword in jobinja_keywords(titles):
            response = requests.get(
                "https://jobinja.ir/jobs",
                params={"filters[keywords][0]": keyword},
                headers={**HEADERS, "Accept": "text/html"},
                timeout=15,
            )
            response.raise_for_status()
            for job in parse_jobinja_html(response.text):
                if job["url"] in seen:
                    continue
                seen.add(job["url"])
                found.append(job)
                if len(found) >= 24:
                    break
        return found, report("Jobinja", found)
    except Exception as exc:
        return [], report("Jobinja", error=short_error(exc))


def jobinja_keywords(titles: list[str]) -> list[str]:
    return board_keywords(titles)


def parse_jobinja_html(page: str) -> list[dict]:
    jobs = []
    for match in JOBINJA_CARD_RE.finditer(page):
        url = unescape(match.group(1)).split("?")[0]
        title = clean_jobinja(match.group(2))
        company = clean_jobinja(match.group(3))
        place = clean_jobinja(match.group(4))
        if not title or not url.startswith("https://jobinja.ir/"):
            continue
        remote = "دورکار" in place or "remote" in place.lower()
        jobs.append(
            base_job(
                source="Jobinja",
                title=title,
                company=company or "Company in Iran",
                location=iran_place(place),
                remote=remote,
                url=url,
                description=title,
                tags=["Iran"],
                published="",
                salary="",
            )
        )
    return jobs


def clean_jobinja(value: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", value or ""))
    text = text.replace("\u200c", " ")
    return re.sub(r"\s+", " ", text).strip(" -|")


IRAN_CITIES = (
    ("تهران", "Tehran, Iran"),
    ("tehran", "Tehran, Iran"),
    ("اصفهان", "Isfahan, Iran"),
    ("isfahan", "Isfahan, Iran"),
    ("esfahan", "Isfahan, Iran"),
    ("کرج", "Karaj, Iran"),
    ("karaj", "Karaj, Iran"),
    ("مشهد", "Mashhad, Iran"),
    ("mashhad", "Mashhad, Iran"),
    ("خراسان رضوی", "Mashhad, Iran"),
    ("شیراز", "Shiraz, Iran"),
    ("shiraz", "Shiraz, Iran"),
    ("فارس", "Shiraz, Iran"),
    ("تبریز", "Tabriz, Iran"),
    ("tabriz", "Tabriz, Iran"),
    ("آذربایجان", "Tabriz, Iran"),
    ("قم", "Qom, Iran"),
    ("یزد", "Yazd, Iran"),
    ("رشت", "Rasht, Iran"),
    ("اهواز", "Ahvaz, Iran"),
)


def iran_place(place: str, remote: bool = False) -> str:
    text = clean_jobinja(place)
    lowered = text.lower()
    label = "Iran"
    for token, city in IRAN_CITIES:
        if token in text or token in lowered:
            label = city
            break
    if remote:
        return f"Remote, {label}"
    return label


def fetch_jobvision(titles: list[str]) -> tuple[list[dict], dict]:
    try:
        found = []
        seen: set[str] = set()
        for keyword in board_keywords(titles):
            response = requests.post(
                "https://candidateapi.jobvision.ir/api/v1/JobPost/List",
                json={"keyword": keyword, "page": 1, "pageSize": 12},
                headers={
                    **HEADERS,
                    "Origin": "https://jobvision.ir",
                    "Referer": "https://jobvision.ir/jobs",
                },
                timeout=18,
            )
            response.raise_for_status()
            for job in parse_jobvision_payload(response.json()):
                if job["url"] in seen:
                    continue
                seen.add(job["url"])
                found.append(job)
                if len(found) >= 18:
                    break
        return found, report("Jobvision", found)
    except Exception as exc:
        return [], report("Jobvision", error=short_error(exc))


def parse_jobvision_payload(payload: dict) -> list[dict]:
    posts = (payload.get("data") or {}).get("jobPosts") or []
    jobs = []
    for item in posts:
        if not isinstance(item, dict):
            continue
        title = clean(item.get("title"))
        job_id = item.get("id")
        if not title or not job_id:
            continue
        company = item.get("company") or {}
        props = item.get("properties") or {}
        remote = bool(props.get("isRemote"))
        categories = [
            clean(cat.get("titleEn") or cat.get("titleFa"))
            for cat in item.get("jobCategories") or []
            if isinstance(cat, dict)
        ]
        jobs.append(
            base_job(
                source="Jobvision",
                title=title,
                company=clean(company.get("nameEn") or company.get("nameFa")) or "Company in Iran",
                location=jobvision_place(item.get("location"), remote),
                remote=remote,
                url=f"https://jobvision.ir/jobs/{job_id}",
                description=" ".join(part for part in [title, *categories] if part),
                tags=["Iran", *categories],
                published=iso_date(item.get("activationTime") or item.get("firstActivationTime")),
                salary=salary_text(item.get("salary")) if props.get("salaryCanBeShown") else "",
            )
        )
    return jobs


def jobvision_place(location, remote: bool) -> str:
    if not isinstance(location, dict):
        return iran_place("", remote)
    city = location.get("city") or {}
    province = location.get("province") or {}
    name = city.get("titleEn") or city.get("titleFa") or province.get("titleEn") or province.get("titleFa") or ""
    return iran_place(str(name), remote)


def fetch_quera(titles: list[str]) -> tuple[list[dict], dict]:
    try:
        found = []
        seen: set[str] = set()
        for keyword in quera_keywords(titles):
            response = requests.get(
                "https://quera.org/magnet/jobs",
                params={"search": keyword},
                headers={**HEADERS, "Accept": "text/html"},
                timeout=18,
            )
            response.raise_for_status()
            for job in parse_quera_html(response.text):
                if job["url"] in seen:
                    continue
                seen.add(job["url"])
                found.append(job)
                if len(found) >= 18:
                    break
        return found, report("Quera", found)
    except Exception as exc:
        return [], report("Quera", error=short_error(exc))


def quera_keywords(titles: list[str]) -> list[str]:
    blob = " ".join(titles).lower()
    keywords = []
    if any(word in blob for word in ("front", "react", "next")):
        keywords.extend(["react", "frontend"])
    if any(word in blob for word in ("back", "backend")):
        keywords.append("back-end")
    if "full" in blob or "stack" in blob:
        keywords.append("fullstack")
    return keywords or board_keywords(titles)


def parse_quera_html(page: str) -> list[dict]:
    data = embedded_json(page, "__NEXT_DATA__")
    if not data:
        return []
    edges = (((data.get("props") or {}).get("pageProps") or {}).get("jobs") or {}).get("edges") or []
    jobs = []
    for edge in edges:
        node = edge.get("node") if isinstance(edge, dict) else None
        if not isinstance(node, dict):
            continue
        if node.get("open") is False:
            continue
        title = clean(node.get("title"))
        job_id = clean(node.get("pk"))
        if not title or not job_id:
            continue
        company = node.get("company") or {}
        city = node.get("city") or {}
        technologies = [
            clean((item.get("technology") or {}).get("name"))
            for item in node.get("jobtechnology_set") or []
            if isinstance(item, dict)
        ]
        remote = bool(node.get("offers_remote"))
        jobs.append(
            base_job(
                source="Quera",
                title=title,
                company=clean(company.get("name")) or "Company in Iran",
                location=iran_place(clean(city.get("name")), remote),
                remote=remote,
                url=f"https://quera.org/magnet/jobs/{job_id}",
                description=" ".join(part for part in [title, *technologies] if part),
                tags=["Iran", *technologies],
                published=iso_date(node.get("publish_time")),
                salary=clean(node.get("salary") or ""),
            )
        )
    return jobs


def fetch_eestekhdam(titles: list[str]) -> tuple[list[dict], dict]:
    try:
        found = []
        seen: set[str] = set()
        headers = {
            **HEADERS,
            "Origin": "https://www.e-estekhdam.com",
            "Referer": "https://www.e-estekhdam.com/",
            "x-lang": "fa",
        }
        for keyword in board_keywords(titles):
            response = requests.post(
                "https://www.e-estekhdam.com/search-api/search",
                json={"query_text": keyword},
                headers=headers,
                timeout=18,
            )
            response.raise_for_status()
            payload = response.json()
            for job in parse_eestekhdam_jobs(payload.get("data") or []):
                if job["url"] in seen:
                    continue
                seen.add(job["url"])
                found.append(job)
                if len(found) >= 18:
                    break
        return found, report("e-Estekhdam", found)
    except Exception as exc:
        return [], report("e-Estekhdam", error=short_error(exc))


def parse_eestekhdam_jobs(items: list) -> list[dict]:
    jobs = []
    for item in items:
        if not isinstance(item, dict) or item.get("expired"):
            continue
        title = clean(item.get("short_title") or item.get("title"))
        path = clean(item.get("url"))
        if not title or not path:
            continue
        contracts = [clean(kind) for kind in item.get("contract") or [] if kind]
        technologies = [clean(name) for name in item.get("technologies") or [] if name]
        remote = any("دورکار" in kind or "remote" in kind.lower() for kind in contracts)
        provinces = item.get("provinces") or []
        place = clean(provinces[0]) if provinces else ""
        if path.startswith("http"):
            url = path
        else:
            url = "https://www.e-estekhdam.com" + (path if path.startswith("/") else f"/{path}")
        jobs.append(
            base_job(
                source="e-Estekhdam",
                title=title,
                company=clean(item.get("brand_name")) or "Company in Iran",
                location=iran_place(place, remote),
                remote=remote,
                url=url.split("?")[0],
                description=" ".join(part for part in [title, clean(item.get("title")), *technologies] if part),
                tags=["Iran", *technologies, *contracts],
                published="",
                salary=clean(item.get("salary") or ""),
            )
        )
    return jobs


def fetch_irantalent(titles: list[str]) -> tuple[list[dict], dict]:
    try:
        found = []
        seen: set[str] = set()
        for keyword in board_keywords(titles):
            response = requests.get(
                "https://www.irantalent.com/jobs",
                params={"keyword": keyword},
                headers={**HEADERS, "Accept": "text/html"},
                timeout=20,
            )
            response.raise_for_status()
            for job in parse_irantalent_html(response.text):
                if job["url"] in seen:
                    continue
                seen.add(job["url"])
                found.append(job)
                if len(found) >= 18:
                    break
        return found, report("IranTalent", found)
    except Exception as exc:
        return [], report("IranTalent", error=short_error(exc))


def parse_irantalent_html(page: str) -> list[dict]:
    data = embedded_json(page, "ng-state")
    if not data:
        return []
    listing = ((data.get("serverSideSearchResult") or {}).get("data") or {}).get("data") or []
    jobs = []
    for item in listing:
        if not isinstance(item, dict):
            continue
        title = clean(item.get("title") or item.get("title_farsi"))
        slug = clean(item.get("slug"))
        job_id = item.get("id")
        if not title or not slug or not job_id:
            continue
        employer = item.get("employer") or {}
        location = item.get("location") or {}
        place = clean(location.get("title") or location.get("title_farsi") or item.get("location_text"))
        work_type = clean(item.get("work_type") or "")
        remote = "remote" in work_type.lower() or "دورکار" in work_type
        jobs.append(
            base_job(
                source="IranTalent",
                title=title,
                company=clean(employer.get("name") or employer.get("name_farsi")) or "Company in Iran",
                location=iran_place(place, remote),
                remote=remote,
                url=f"https://www.irantalent.com/job/{slug}/{job_id}",
                description=" ".join(
                    part
                    for part in [title, clean(item.get("title_farsi")), html_to_text(item.get("role_description") or "")]
                    if part
                ),
                tags=["Iran"],
                published=iso_date(item.get("lived_at") or item.get("created_at")),
                salary=salary_range(item.get("salary_from"), item.get("salary_to")),
            )
        )
    return jobs


def fetch_kardix(titles: list[str]) -> tuple[list[dict], dict]:
    try:
        found = []
        seen: set[str] = set()
        slugs = kardix_slugs(titles)
        if not slugs:
            return [], report("Kardix", [])
        for slug in slugs:
            response = requests.get(
                f"https://kardix.com/jobs/q-{slug}",
                headers={**HEADERS, "Accept": "text/html"},
                timeout=18,
            )
            response.raise_for_status()
            for job in parse_kardix_html(response.text):
                if job["url"] in seen:
                    continue
                seen.add(job["url"])
                found.append(job)
                if len(found) >= 18:
                    break
        return found, report("Kardix", found)
    except Exception as exc:
        return [], report("Kardix", error=short_error(exc))


def kardix_slugs(titles: list[str]) -> list[str]:
    blob = " ".join(titles).lower()
    slugs = []
    if any(word in blob for word in ("front", "react", "next")):
        slugs.extend(["front-end-developer", "react-developer"])
    if any(word in blob for word in ("back", "backend")):
        slugs.append("back-end-developer")
    if "node" in blob:
        slugs.append("nodejs")
    if "java" in blob and "javascript" not in blob:
        slugs.append("java-developer")
    if "python" in blob:
        slugs.append("python-developer")
    if "full" in blob or "stack" in blob:
        slugs.append("full-stack-developer")
    if not slugs and not blob:
        slugs.append("front-end-developer")
    return slugs


def parse_kardix_html(page: str) -> list[dict]:
    data = embedded_json(page, "__NEXT_DATA__")
    if not data:
        return []
    queries = (((data.get("props") or {}).get("pageProps") or {}).get("dehydratedState") or {}).get("queries") or []
    items: list = []
    for query in queries:
        payload = ((query or {}).get("state") or {}).get("data") or {}
        rows = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(rows, list):
            items.extend(rows)
    return parse_kardix_jobs(items)


def parse_kardix_jobs(items: list) -> list[dict]:
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = clean(item.get("title"))
        job_id = item.get("id")
        if not title or not job_id:
            continue
        company = item.get("company") or {}
        city = item.get("city") or {}
        region = item.get("location") or {}
        place = clean(city.get("title") or region.get("title"))
        employment = clean(item.get("employment_type") or "")
        remote = employment in {"remote", "work_from_home"} or "دورکار" in title
        jobs.append(
            base_job(
                source="Kardix",
                title=title,
                company=clean(company.get("title")) or "Company in Iran",
                location=iran_place(place, remote),
                remote=remote,
                url=f"https://kardix.com/jobs/{job_id}",
                description=" ".join(part for part in [title, html_to_text(item.get("conditions") or "")] if part),
                tags=["Iran", employment],
                published=iso_date(item.get("published_at")),
                salary=clean(item.get("salary") or ""),
            )
        )
    return jobs


def board_keywords(titles: list[str]) -> list[str]:
    blob = " ".join(titles).lower()
    keywords = []
    if any(word in blob for word in ("front", "react", "next")):
        keywords.append("frontend")
    if any(word in blob for word in ("back", "backend")):
        keywords.append("backend")
    if "full" in blob or "stack" in blob:
        keywords.append("full stack")
    if not keywords:
        keywords.extend(title for title in titles[:2] if title)
    return keywords or ["frontend"]


def embedded_json(page: str, script_id: str) -> dict | None:
    match = re.search(
        rf'<script id="{re.escape(script_id)}" type="application/json">(.*?)</script>',
        page,
        re.S,
    )
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def salary_text(value) -> str:
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, dict):
        return clean(value.get("title") or value.get("titleFa") or value.get("titleEn") or "")
    return ""


def salary_range(low, high) -> str:
    if low and high:
        return f"{low}-{high}"
    return clean(low or high or "")


def role_tag(title: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z+#]{2,}", title)
    generic = {"senior", "junior", "lead", "principal", "staff", "head", "the", "and"}
    specific = [word for word in words if word.lower() not in generic]
    return specific[-1] if specific else (words[-1] if words else "")


def adapt_remotive(item: dict) -> dict | None:
    title = clean(item.get("title"))
    if not title:
        return None
    location = clean(item.get("candidate_required_location")) or "Remote"
    return base_job(
        source="Remotive",
        title=title,
        company=clean(item.get("company_name")) or "Unknown company",
        location=location,
        remote=True,
        url=clean(item.get("url")),
        description=html_to_text(item.get("description") or ""),
        tags=[clean(item.get("category") or ""), clean(item.get("job_type") or "")],
        published=iso_date(item.get("publication_date")),
        salary=clean(item.get("salary")),
    )


def adapt_arbeitnow(item: dict) -> dict | None:
    title = clean(item.get("title"))
    if not title:
        return None
    remote = bool(item.get("remote"))
    location = clean(item.get("location")) or ("Remote" if remote else "")
    tags = [str(tag) for tag in item.get("tags") or [] if tag]
    tags.extend(str(kind) for kind in item.get("job_types") or [] if kind)
    return base_job(
        source="Arbeitnow",
        title=title,
        company=clean(item.get("company_name")) or "Unknown company",
        location=location,
        remote=remote or "remote" in location.lower(),
        url=clean(item.get("url")),
        description=html_to_text(item.get("description") or ""),
        tags=tags,
        published=iso_date(item.get("created_at")),
        salary="",
    )


def adapt_remoteok(item: dict) -> dict | None:
    title = clean(item.get("position"))
    if not title:
        return None
    location = clean(item.get("location")) or "Remote"
    tags = [str(tag) for tag in item.get("tags") or [] if isinstance(tag, str)]
    salary = clean(item.get("salary"))
    if not salary and item.get("salary_min") and item.get("salary_max"):
        salary = f"{item['salary_min']}-{item['salary_max']}"
    return base_job(
        source="Remote OK",
        title=title,
        company=clean(item.get("company")) or "Unknown company",
        location=location,
        remote=True,
        url=clean(item.get("url")) or clean(item.get("apply_url")),
        description=html_to_text(item.get("description") or ""),
        tags=tags,
        published=iso_date(item.get("epoch") or item.get("date")),
        salary=salary,
    )


def adapt_jobicy(item: dict) -> dict | None:
    title = clean(item.get("jobTitle"))
    if not title:
        return None
    location = clean(item.get("jobGeo")) or "Remote"
    kinds = item.get("jobType") or []
    if isinstance(kinds, str):
        kinds = [kinds]
    return base_job(
        source="Jobicy",
        title=title,
        company=clean(item.get("companyName")) or "Unknown company",
        location=location,
        remote=True,
        url=clean(item.get("url")),
        description=html_to_text(item.get("jobDescription") or item.get("jobExcerpt") or ""),
        tags=[str(kind) for kind in kinds if kind],
        published=iso_date(item.get("pubDate")),
        salary=clean(item.get("salary")),
    )


def base_job(
    *,
    source: str,
    title: str,
    company: str,
    location: str,
    remote: bool,
    url: str,
    description: str,
    tags: list[str],
    published: str,
    salary: str,
) -> dict:
    return {
        "source": source,
        "title": title,
        "company": company,
        "location": location,
        "remote": remote,
        "url": url,
        "description": description[:8000],
        "tags": [tag for tag in tags if tag][:12],
        "published": published,
        "salary": salary,
    }


def dedupe_jobs(jobs: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    unique = []
    for job in jobs:
        url = (job.get("url") or "").split("?")[0].rstrip("/").lower()
        key = ("url", url) if url else ("tc", job["title"].lower(), job["company"].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def report(name: str, jobs: list[dict] | None = None, error: str = "") -> dict:
    found = jobs or []
    return {
        "name": name,
        "ok": not error,
        "count": len(found),
        "error": error,
    }


def short_error(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    return (text[0] if text else exc.__class__.__name__)[:180]


def clean(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()
