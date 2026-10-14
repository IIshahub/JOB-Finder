"""Read a CV and pull out contact details, skills, and target roles."""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path

SKILLS = [
    "Python", "Java", "JavaScript", "TypeScript", "C#", "C++", "Rust", "PHP", "Ruby",
    "Swift", "Kotlin", "SQL", "NoSQL", "HTML", "CSS", "React", "Angular", "Vue",
    "Node.js", "Next.js", "Django", "Flask", "FastAPI", "Fastify", "Spring", ".NET", "ASP.NET", "Laravel",
    "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Linux", "Git", "REST", "GraphQL",
    "MongoDB", "PostgreSQL", "MySQL", "Redis", "Prisma", "Tailwind CSS", "Bootstrap",
    "Material UI", "Ant Design", "jQuery", "Zod", "Postman", "Tableau", "Power BI", "Excel",
    "Looker", "Figma", "Adobe Photoshop", "Adobe Illustrator", "Jira", "Salesforce",
    "SAP", "Oracle", "TensorFlow", "PyTorch", "Machine Learning", "Deep Learning",
    "NLP", "Computer Vision", "Pandas", "NumPy", "scikit-learn", "Statistics",
    "A/B testing", "ETL", "Airflow", "Snowflake", "BigQuery", "Terraform", "CI/CD",
    "Agile", "Scrum", "Kafka", "Elasticsearch", "PowerPoint", "Microsoft Office",
    "Google Sheets", "AutoCAD", "SolidWorks", "MATLAB", "SPSS", "Project Management",
    "Product Management", "Business Analysis", "Financial Analysis", "Accounting",
    "Bookkeeping", "IFRS", "Auditing", "Budgeting", "Forecasting", "Procurement",
    "Supply Chain", "Logistics", "Customer Service", "Human Resources", "Recruiting",
    "Talent Acquisition", "Payroll", "SEO", "SEM", "Google Analytics", "Copywriting",
    "Social Media", "CRM", "Negotiation", "Market Research", "Business Development",
    "Stakeholder Management", "QuickBooks", "Risk Management", "Compliance",
    "UX Research", "Wireframing", "Prototyping", "Nursing", "Patient Care",
    "Clinical Research", "Teaching", "Curriculum Development", "Translation",
    "Customer Success", "Technical Support", "Quality Assurance", "Manual Testing",
    "Test Automation", "Cypress", "Selenium", "Unit Testing", "Data Analysis",
    "Data Science", "Data Engineering", "Business Intelligence", "Financial Modeling",
    "Microsoft Excel", "Customer Support", "Account Management", "Digital Marketing",
    "Content Marketing", "Email Marketing", "Sales Management", "Cold Calling",
    "Public Speaking", "Grant Writing", "Legal Research", "Contract Review",
    "Inventory Management", "Warehouse Management", "Electrical Engineering",
    "Mechanical Engineering", "Civil Engineering", "Project Planning",
]

ALIASES = {
    "js": "JavaScript",
    "ts": "TypeScript",
    "nodejs": "Node.js",
    "node": "Node.js",
    "reactjs": "React",
    "react.js": "React",
    "react js": "React",
    "nextjs": "Next.js",
    "next js": "Next.js",
    "html5": "HTML",
    "css3": "CSS",
    "rest api": "REST",
    "rest apis": "REST",
    "mui": "Material UI",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mongodb": "MongoDB",
    "powerbi": "Power BI",
    "power-bi": "Power BI",
    "ml": "Machine Learning",
    "ai": "Machine Learning",
    "ab testing": "A/B testing",
    "a/b tests": "A/B testing",
    "ms excel": "Excel",
    "microsoft excel": "Excel",
    "google bigquery": "BigQuery",
    "nodejs.js": "Node.js",
}

AMBIGUOUS = {
    "Sales", "Marketing", "Design", "Support", "Management", "Research", "Training",
    "Service", "Finance", "Writing", "Planning", "Operations", "Strategy", "Content",
    "Human Resources", "Translation", "Budgeting", "Quality Assurance",
}

SECTION_ONLY = {"Go", "R", "C"}

HEADINGS = {
    "summary": "summary",
    "professional summary": "summary",
    "career summary": "summary",
    "executive summary": "summary",
    "profile": "summary",
    "personal profile": "summary",
    "about me": "summary",
    "about": "summary",
    "objective": "summary",
    "career objective": "summary",
    "personal statement": "summary",
    "skills": "skills",
    "key skills": "skills",
    "technical skills": "skills",
    "core skills": "skills",
    "core competencies": "skills",
    "competencies": "skills",
    "areas of expertise": "skills",
    "expertise": "skills",
    "technologies": "skills",
    "tech stack": "skills",
    "tools": "skills",
    "tools & technologies": "skills",
    "tools and technologies": "skills",
    "languages": "skills",
    "hard skills": "skills",
    "software": "skills",
    "experience": "experience",
    "work experience": "experience",
    "work experiences": "experience",
    "professional experience": "experience",
    "professional experiences": "experience",
    "relevant experience": "experience",
    "employment": "experience",
    "employment history": "experience",
    "work history": "experience",
    "career history": "experience",
    "professional background": "experience",
    "education": "other",
    "academic background": "other",
    "projects": "other",
    "personal projects": "other",
    "certifications": "other",
    "certificates": "other",
    "awards": "other",
    "interests": "other",
    "hobbies": "other",
    "references": "other",
    "contact": "other",
    "contact information": "other",
    # Persian section titles common on Iranian CVs.
    "خلاصه": "summary",
    "خلاصه حرفه ای": "summary",
    "درباره من": "summary",
    "معرفی": "summary",
    "هدف شغلی": "summary",
    "مهارت ها": "skills",
    "مهارت‌ها": "skills",
    "مهارتها": "skills",
    "مهارت های فنی": "skills",
    "مهارت‌های فنی": "skills",
    "توانایی ها": "skills",
    "توانایی‌ها": "skills",
    "تکنولوژی ها": "skills",
    "تکنولوژی‌ها": "skills",
    "تجربه کاری": "experience",
    "تجربیات کاری": "experience",
    "سوابق شغلی": "experience",
    "سوابق کاری": "experience",
    "سابقه کاری": "experience",
    "تحصیلات": "other",
    "سوابق تحصیلی": "other",
    "پروژه ها": "other",
    "پروژه‌ها": "other",
    "گواهینامه ها": "other",
    "گواهینامه‌ها": "other",
    "اطلاعات تماس": "other",
    "مهارت": "skills",
    "مهارت های نرم افزاری": "skills",
    "مهارت های تخصصی": "skills",
    "زبان ها": "skills",
    "تجربیات": "experience",
    "سوابق": "experience",
    "سوابق حرفه ای": "experience",
    "تحصیلات دانشگاهی": "other",
    "دوره ها": "other",
    "علاقه مندی ها": "other",
}

# Words that make a short line a section heading, e.g. "Professional Skills",
# "Experience & Projects", or "Work History".
HEADING_WORDS = {
    "summary": "summary", "profile": "summary", "objective": "summary", "about": "summary",
    "statement": "summary", "overview": "summary", "introduction": "summary", "bio": "summary",
    "skills": "skills", "skill": "skills", "competencies": "skills", "competences": "skills",
    "expertise": "skills", "technologies": "skills", "stack": "skills", "tools": "skills",
    "proficiencies": "skills", "abilities": "skills", "strengths": "skills", "languages": "skills",
    "toolbox": "skills", "toolkit": "skills",
    "experience": "experience", "experiences": "experience", "employment": "experience",
    "history": "experience", "positions": "experience", "internships": "experience",
    "internship": "experience",
    "education": "other", "projects": "other", "certifications": "other", "certificates": "other",
    "courses": "other", "coursework": "other", "training": "other", "trainings": "other",
    "awards": "other", "achievements": "other", "honors": "other", "honours": "other",
    "interests": "other", "hobbies": "other", "references": "other", "publications": "other",
    "volunteering": "other", "activities": "other", "contact": "other", "details": "other",
    "information": "other", "info": "other", "accomplishments": "other",
}
HEADING_FILLERS = {
    "work", "professional", "technical", "key", "core", "relevant", "my", "and", "&", "of",
    "soft", "hard", "other", "additional", "selected", "personal", "academic", "career",
    "computer", "it", "software", "programming", "language", "industry", "leadership",
    "research", "teaching", "volunteer", "areas", "area", "main", "previous", "recent",
    "related", "notable", "featured", "transferable", "functional", "management", "business",
    "digital", "design", "development", "data", "tech", "short", "brief", "executive",
    "background", "job", "military", "service", "extracurricular", "side", "open", "source",
    "the", "me", "qualifications",
}
HEADING_SQUASHED = {key.replace(" ", ""): kind for key, kind in HEADINGS.items() if key.isascii()}
HEADING_SQUASHED.update(HEADING_WORDS)
INLINE_LABEL_RE = re.compile(r"^([^:：]{2,40})[:：]\s*(\S.*)$")

TITLE_HINT = re.compile(
    r"\b(engineer|engineering|developer|designer|manager|analyst|scientist|"
    r"consultant|specialist|coordinator|assistant|director|intern|officer|"
    r"architect|administrator|accountant|nurse|teacher|recruiter|marketer|"
    r"marketing|writer|editor|lawyer|attorney|salesperson|representative|"
    r"technician|mechanic|supervisor|associate|executive|founder|researcher|"
    r"pharmacist|therapist|chef|planner|buyer|programmer|president|"
    r"administrator|head|lead|devops|frontend|backend|fullstack|"
    r"full[- ]?stack|front[- ]?end|back[- ]?end|physician|doctor|dentist|"
    r"translator|interpreter|photographer|journalist|copywriter|auditor|"
    r"economist|statistician|electrician|operator|clerk|cashier|receptionist|"
    r"secretary|tester|instructor|tutor|lecturer|professor|advisor|adviser|"
    r"strategist|trainer|producer|artist|illustrator|animator|agent|"
    r"paralegal|counsel|surveyor|pilot|driver|bookkeeper|controller|"
    r"owner|partner|sre|qa)\b",
    re.I,
)

# Job titles that are clear on their own, e.g. a headline that only says "Accountant".
SINGLE_TITLES = {
    "developer", "programmer", "engineer", "designer", "accountant", "nurse", "teacher",
    "translator", "interpreter", "architect", "analyst", "consultant", "lawyer", "attorney",
    "pharmacist", "physician", "dentist", "photographer", "journalist", "editor", "writer",
    "copywriter", "recruiter", "economist", "auditor", "electrician", "mechanic", "technician",
    "chef", "cashier", "receptionist", "secretary", "tester", "illustrator", "animator",
    "researcher", "lecturer", "tutor", "instructor", "marketer", "bookkeeper", "paralegal",
}

PERSIAN_TITLE_RE = re.compile(
    r"(برنامه[\s‌]*نویس|توسعه[\s‌]*دهنده|مهندس|تحلیلگر|طراح|مدیر|"
    r"فرانت[\s‌\-]*اند|بک[\s‌\-]*اند|فول[\s‌\-]*استک|کارشناس|حسابدار|"
    r"پشتیبان|مترجم|مدرس|معلم|پرستار|تکنسین|اپراتور|سرپرست|کارآموز|"
    r"بازاریاب|گرافیست|حسابرس|منشی|مشاور)",
)

NAME_WORD_RE = re.compile(r"[A-Za-z\u0600-\u06FF][A-Za-z\u0600-\u06FF.'-]*")
COUNTRY_HINTS = (
    "Iran", "Tehran", "Isfahan", "Mashhad", "Shiraz", "Tabriz", "Karaj",
    "Germany", "Berlin", "Munich", "Austria", "Vienna", "Netherlands", "Amsterdam",
    "United Kingdom", "London", "France", "Paris", "Canada", "Toronto", "Vancouver",
    "United States", "USA", "Turkey", "Istanbul", "United Arab Emirates", "Dubai",
    "Portugal", "Lisbon", "Spain", "Madrid", "Italy", "Poland", "Sweden", "Norway",
    "Denmark", "Finland", "Ireland", "Belgium", "Switzerland", "Australia",
    "ایران", "تهران", "اصفهان", "مشهد", "شیراز", "تبریز", "کرج",
)
LOCATION_PREFIX_RE = re.compile(
    r"^(?:location|address|city|based in|residing in|lives? in|اقامت|محل سکونت|شهر)\s*[:|\-]?\s*(.+)$",
    re.I,
)

ACTION_START = re.compile(
    r"^(led|built|managed|improved|developed|created|worked|responsible|helped|"
    r"achieved|increased|reduced|designed|implemented|supported|delivered|"
    r"collaborated|assisted|organized|prepared|maintained|used|using|"
    r"responsible)\b",
    re.I,
)

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?<![\w+])\+?\(?\d[\d \t().-]{6,18}\d(?!\d)")
YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
LOCAL_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
NAME_PREFIX_RE = re.compile(r"^(?:full name|name|نام و نام خانوادگی|نام)\s*[:：]\s*(.+)$", re.I)
SKILL_LEVEL_RE = re.compile(
    r"(?:\s*\d{1,3}\s*%|\s*[★☆●○◉◯■□▪▫]+|\s*[-–:|]\s*(?:expert|advanced|intermediate|"
    r"proficient|basic|good|excellent|fluent|native|upper[- ]intermediate))\s*$",
    re.I,
)
LINKEDIN_RE = re.compile(r"https?://(?:[\w.]+)?linkedin\.com/in/[\w\-_%]+/?", re.I)
PLACE_RE = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:\s*,\s*[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)+)\b"
)
PERSIAN_PLACE_RE = re.compile(r"([\u0600-\u06FF][\u0600-\u06FF\s‌]{1,30})\s*[،,]\s*([\u0600-\u06FF][\u0600-\u06FF\s‌]{1,20})")
SKILL_LABEL_RE = re.compile(
    r"^(?:languages|language|technologies|technology|tools|frameworks|libraries|databases|database|other|soft skills|"
    r"مهارت ها|مهارت‌ها|زبان ها|زبان‌ها|تکنولوژی ها|تکنولوژی‌ها)\s*:\s*",
    re.I,
)
SKILL_STOP = {"apis", "api", "beginner", "present", "part-time", "part time", "skills", "technologies"}
# Spoken languages often share a "Languages" section with programming languages.
SPOKEN_LANGUAGES = {
    "english", "persian", "farsi", "arabic", "french", "german", "spanish", "turkish",
    "russian", "italian", "chinese", "mandarin", "japanese", "korean", "portuguese", "dutch",
    "hindi", "urdu", "azerbaijani", "azeri", "kurdish", "swedish", "polish", "greek",
    "انگلیسی", "فارسی", "عربی", "فرانسوی", "آلمانی", "ترکی",
}
SKILL_STOP |= SPOKEN_LANGUAGES


def _canonical_map() -> dict[str, str]:
    mapping = {skill.lower(): skill for skill in SKILLS}
    mapping.update(ALIASES)
    for skill in SECTION_ONLY:
        mapping[skill.lower()] = skill
    return mapping


CANONICAL = _canonical_map()

_TERMS = sorted(CANONICAL, key=len, reverse=True)
_SKILL_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(term) for term in _TERMS) + r")(?!\w)",
    re.I,
)


PDF_LOCKED = "This PDF is password-protected. Export an unlocked copy or paste the text."
PDF_TOO_LONG = "That PDF has too many pages for a CV. Paste the text instead."
MAX_PDF_PAGES = 30


def read_upload(filename: str, data: bytes) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext == ".pdf":
        text = read_pdf(data)
    elif ext == ".docx":
        text = read_docx(data)
    elif ext == ".txt":
        text = decode_text(data)
    else:
        raise ValueError("Upload a PDF, DOCX, or TXT file.")

    text = normalize_text(text)
    if len(text) < 40:
        raise ValueError(
            "Could not read enough text from that file. If it is a scanned PDF, paste the CV text instead."
        )
    return text


def decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("cp1256", errors="replace")


def read_pdf(data: bytes) -> str:
    try:
        text = read_pdf_columns(data)
    except ValueError as exc:
        if str(exc) in {PDF_LOCKED, PDF_TOO_LONG}:
            raise
        text = ""
    except Exception:
        text = ""
    if len(normalize_text(text)) >= 40:
        return text
    return read_pdf_plain(data)


def read_pdf_columns(data: bytes) -> str:
    """Read each page block by block, one column at a time.

    Plain text extraction reads straight across the page, which interleaves
    the sidebar and main column of two-column CV templates.
    """
    import pymupdf

    document = pymupdf.open(stream=data, filetype="pdf")
    try:
        if document.needs_pass and not document.authenticate(""):
            raise ValueError(PDF_LOCKED)
        if document.page_count > MAX_PDF_PAGES:
            raise ValueError(PDF_TOO_LONG)
        pages = []
        for page in document:
            blocks = [
                (x0, y0, x1, y1, text)
                for x0, y0, x1, y1, text, _number, kind in page.get_text("blocks")
                if kind == 0 and text.strip()
            ]
            pages.append("\n".join(column_order(blocks, page.rect.width)))
        return "\n\n".join(pages)
    finally:
        document.close()


def read_pdf_plain(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValueError(PDF_LOCKED) from exc
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError(PDF_TOO_LONG)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def column_order(blocks: list[tuple], width: float) -> list[str]:
    """Order text blocks top to bottom, reading a left column before a right one.

    Blocks that span both columns (a name banner, a full-width paragraph) are
    kept in place and close the columns above them.
    """
    blocks = sorted(blocks, key=lambda block: (round(block[1]), block[0]))
    split = column_split(blocks, width)
    if split is None:
        return [block[4].strip() for block in blocks]

    ordered: list[str] = []
    left: list[tuple] = []
    right: list[tuple] = []

    def flush() -> None:
        ordered.extend(block[4].strip() for block in left)
        ordered.extend(block[4].strip() for block in right)
        left.clear()
        right.clear()

    for block in blocks:
        if block[2] <= split:
            left.append(block)
        elif block[0] >= split:
            right.append(block)
        else:
            flush()
            ordered.append(block[4].strip())
    flush()
    return ordered


def column_split(blocks: list[tuple], width: float) -> float | None:
    if len(blocks) < 4 or width <= 0:
        return None
    best = None
    for step in range(20, 81, 2):
        split = width * step / 100
        left = sum(1 for block in blocks if block[2] <= split)
        right = sum(1 for block in blocks if block[0] >= split)
        crossing = len(blocks) - left - right
        if min(left, right) < 3 or crossing > len(blocks) * 0.3:
            continue
        key = (crossing, -min(left, right))
        if best is None or key < best[0]:
            best = (key, split)
    return best[1] if best else None


WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FALLBACK_TAG = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"


def read_docx(data: bytes) -> str:
    """Read body text, tables, text boxes, and headers in document order.

    Many CV templates keep the name and contact details in the page header or
    in text boxes, which python-docx's paragraph list leaves out.
    """
    assert_docx_limits(data)
    from lxml import etree

    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    parts: list[str] = []
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = archive.namelist()
            headers = sorted(name for name in names if re.fullmatch(r"word/header\d*\.xml", name))
            for name in [*headers, "word/document.xml"]:
                if name not in names:
                    continue
                root = etree.fromstring(archive.read(name), parser)
                parts.extend(docx_paragraphs(root))
    except (zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        raise ValueError("That file could not be read. Try PDF, DOCX, or paste the text.") from exc
    return "\n".join(parts)


def docx_paragraphs(root) -> list[str]:
    paragraph_tag = f"{WORD_NS}p"
    lines = []
    for paragraph in root.iter(paragraph_tag):
        # Text boxes are stored twice: once for new Word and once as a fallback.
        if any(ancestor.tag == FALLBACK_TAG for ancestor in paragraph.iterancestors()):
            continue
        pieces = []
        for node in paragraph.iter(f"{WORD_NS}t", f"{WORD_NS}tab", f"{WORD_NS}br", f"{WORD_NS}cr"):
            if next(node.iterancestors(paragraph_tag), None) is not paragraph:
                continue
            if node.tag == f"{WORD_NS}t":
                pieces.append(node.text or "")
            elif node.tag == f"{WORD_NS}tab":
                pieces.append(" ")
            else:
                pieces.append("\n")
        text = "".join(pieces).strip()
        if text:
            lines.append(text)
    return lines


def assert_docx_limits(data: bytes) -> None:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            total = 0
            for info in archive.infolist():
                total += info.file_size
                if info.file_size > 20 * 1024 * 1024 or total > 20 * 1024 * 1024:
                    raise ValueError("That DOCX is too large to read. Paste the CV text instead.")
    except zipfile.BadZipFile as exc:
        raise ValueError("That file could not be read. Try PDF, DOCX, or paste the text.") from exc


def normalize_text(text: str) -> str:
    text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
    text = text.replace("\u00a0", " ").replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_upload(filename: str, data: bytes) -> tuple[dict, dict]:
    text = read_upload(filename, data)
    profile, reader = read_cv(text)
    profile["cv_filename"] = Path(filename).name
    return profile, reader


def read_cv(text: str) -> tuple[dict, dict]:
    """Parse a CV with the AI reader when a key is set, else with the rules.

    Returns the profile and a note on which reader was used. Fields the AI
    leaves empty are filled from the rules.
    """
    from matcher.cv_ai import AiReadError, ai_configured, ai_parse

    profile = parse_cv(text)
    if not ai_configured():
        return profile, {"reader": "rules", "error": "", "model": ""}
    try:
        found, model = ai_parse(profile["cv_text"])
    except AiReadError as exc:
        return profile, {
            "reader": "rules",
            "error": f"{exc} The basic reader was used instead.",
            "model": "",
        }
    for field in ("name", "email", "phone", "location", "linkedin", "summary"):
        if found[field]:
            profile[field] = found[field]
    if profile["name"].isupper():
        profile["name"] = profile["name"].title()
    if found["skills"]:
        profile["skills"] = canonical_skills(found["skills"])
    if found["target_titles"]:
        profile["target_titles"] = found["target_titles"]
    return profile, {"reader": "ai", "error": "", "model": model}


def canonical_skills(skills: list[str]) -> list[str]:
    found = []
    seen = set()
    for skill in skills:
        canon = CANONICAL.get(skill.lower(), skill)
        if canon.lower() in seen:
            continue
        seen.add(canon.lower())
        found.append(canon)
    return found[:40]


def parse_cv(text: str) -> dict:
    text = normalize_text(text)
    lines = [clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    sections = split_sections(lines)

    skills = extract_skills(text, sections.get("skills", []))
    titles = extract_titles(lines, sections.get("experience", []))
    summary = extract_summary(sections.get("summary", []), lines)
    email = first_match(EMAIL_RE, text)
    linkedin = first_match(LINKEDIN_RE, text)
    phone = extract_phone(text)
    location = extract_location(lines)
    name = extract_name(lines, email)
    if name.isupper():
        name = name.title()

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "location": location,
        "linkedin": linkedin,
        "summary": summary[:600],
        "skills": skills[:40],
        "target_titles": titles[:6],
        "cv_text": text[:200000],
        "cv_filename": "",
    }


def clean_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^[\s•\-\*\u2022\u00b7]+", "", line)
    return re.sub(r"\s+", " ", line).strip()


def split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"preamble": []}
    current = "preamble"
    for line in lines:
        heading = heading_name(line)
        if heading:
            current = heading
            sections.setdefault(current, [])
            continue
        # "Skills: React, SQL" files the rest of the line under that section
        # without ending the section the line sits in.
        inline = INLINE_LABEL_RE.match(line)
        label = heading_name(inline.group(1)) if inline else None
        if label:
            sections.setdefault(label, []).append(inline.group(2))
            continue
        sections.setdefault(current, []).append(line)
    return sections


def heading_name(line: str) -> str | None:
    if len(line) > 50 or "@" in line:
        return None
    cleaned = line.replace("\u200c", " ")
    # Icons, emoji, and decorations around the heading text.
    cleaned = re.sub(r"^[^\w\u0600-\u06FF]+|[^\w\u0600-\u06FF&)]+$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    if not cleaned:
        return None
    if cleaned in HEADINGS:
        return HEADINGS[cleaned]
    # Some PDFs put a section number in front, e.g. "03 Experience".
    numbered = re.sub(r"^\d{1,2}[.)\s]+", "", cleaned).strip()
    if numbered in HEADINGS:
        return HEADINGS[numbered]
    if persian_heading(numbered):
        return persian_heading(numbered)
    words = re.findall(r"[a-z&']+|\S", numbered)
    # Letter-spaced headings such as "S K I L L S" or "W O R K  E X P E R I E N C E".
    if len(words) >= 4 and all(len(word) == 1 for word in words):
        return HEADING_SQUASHED.get("".join(words))
    if not words or len(words) > 5 or re.search(r"\d", numbered):
        return None
    kinds = [HEADING_WORDS[word] for word in words if word in HEADING_WORDS]
    if not kinds:
        return None
    if all(word in HEADING_WORDS or word in HEADING_FILLERS for word in words):
        return kinds[0]
    return None


def persian_heading(text: str) -> str | None:
    if not re.search(r"[\u0600-\u06FF]", text) or len(text.split()) > 4:
        return None
    squashed = re.sub(r"[\s\u200c]+", " ", text).strip()
    for key, kind in HEADINGS.items():
        if key.isascii():
            continue
        if squashed == re.sub(r"[\s\u200c]+", " ", key):
            return kind
    return None


def extract_skills(text: str, skill_lines: list[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(skill: str) -> None:
        skill = " ".join(skill.split())
        skill = re.sub(r"\s*\([^)]*\)", "", skill).strip(" .-:")
        if not skill or skill.lower() in SKILL_STOP:
            return
        key = skill.lower()
        canon = CANONICAL.get(key, skill)
        if canon.lower() in seen:
            return
        seen.add(canon.lower())
        found.append(canon)

    section_text = "\n".join(skill_lines)
    beginner = beginner_skills(section_text)
    for token in split_skill_tokens(section_text):
        if token.lower() in beginner:
            continue
        add(token)

    counts: dict[str, int] = {}
    for match in _SKILL_RE.finditer(text):
        canon = CANONICAL[match.group(0).lower()]
        if canon in SECTION_ONLY:
            continue
        counts[canon] = counts.get(canon, 0) + 1

    section_keys = {item.lower() for item in found}
    for canon, count in counts.items():
        if canon.lower() in beginner:
            continue
        if canon in AMBIGUOUS and count < 2 and canon.lower() not in section_keys:
            continue
        add(canon)
    return found


def beginner_skills(text: str) -> set[str]:
    found = set()
    for item in re.split(r"[,،;/|\n•·]", text):
        if not re.search(r"\bbeginner\b", item, re.I):
            continue
        token = SKILL_LABEL_RE.sub("", " ".join(item.split()))
        token = re.sub(r"\s*\([^)]*\)", "", token).strip(" .-:")
        if not token:
            continue
        found.add(CANONICAL.get(token.lower(), token).lower())
    return found


def split_skill_tokens(text: str) -> list[str]:
    if not text:
        return []
    raw = re.split(r"[,،;/|\n•·]|(?:\s+\band\b\s+)", text, flags=re.I)
    tokens = []
    for item in raw:
        token = SKILL_LABEL_RE.sub("", " ".join(item.split())).strip(" .-:")
        token = re.sub(r"\s*\([^)]*\)", "", token).strip(" .-:")
        token = SKILL_LEVEL_RE.sub("", token).strip(" .-:")
        if not token or len(token) < 2 or len(token) > 40:
            continue
        if len(token.split()) > 5:
            continue
        if "@" in token or "http" in token.lower():
            continue
        if token.lower() in SKILL_STOP or token.lower() in {"and", "or", "the", "with", "for", "from"}:
            continue
        if re.search(r"\b(?:19|20)\d{2}\b", token) or heading_name(token):
            continue
        tokens.append(token)
    return tokens


def extract_titles(lines: list[str], experience_lines: list[str]) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        candidate = tidy_title(candidate)
        if not title_like(candidate):
            return
        key = re.sub(r"[\s‌\-]+", " ", candidate.lower()).strip()
        if key in seen:
            return
        seen.add(key)
        titles.append(candidate)

    # Headline under the name, or a contact line that embeds the role.
    for line in lines[:12]:
        consider_title_line(line, add)
        if titles:
            break

    for line in experience_lines:
        consider_title_line(line, add)
    return titles


def tidy_title(candidate: str) -> str:
    candidate = candidate.replace("\u200c", " ")
    candidate = re.sub(r"\s*\([^)]*\)", "", candidate)
    candidate = re.split(r"[,/|]", candidate)[0]
    return " ".join(candidate.split()).strip(" -|")


def consider_title_line(line: str, add) -> None:
    if "|" in line or " - " in line or " – " in line or " — " in line or " @ " in line.lower():
        parts = re.split(r"\s+(?:[|@]|[-–—]|at)\s+", line, flags=re.I)
        matched = [part for part in parts if title_like(part)]
        if matched:
            add(matched[0])
            return
    add(line)


def title_like(line: str) -> bool:
    line = " ".join(line.replace("\u200c", " ").split()).strip()
    if not line or len(line) < 3 or len(line) > 80:
        return False
    words = line.split()
    if PERSIAN_TITLE_RE.search(line):
        return 1 <= len(words) <= 8 and "@" not in line and not ACTION_START.match(line)
    if len(words) == 1:
        return words[0].lower().strip(".:") in SINGLE_TITLES
    if len(words) > 7:
        return False
    if "@" in line or "%" in line or line.count(",") > 1:
        return False
    if re.search(r"\d", line):
        return False
    if ACTION_START.match(line):
        return False
    if heading_name(line):
        return False
    return TITLE_HINT.search(line) is not None


def extract_summary(summary_lines: list[str], lines: list[str]) -> str:
    if summary_lines:
        text = " ".join(summary_lines)
        return text[:600]
    for line in lines:
        if len(line) >= 80 and not title_like(line) and "@" not in line:
            return line[:600]
    return ""


def extract_name(lines: list[str], email: str) -> str:
    for line in lines[:20]:
        labelled = NAME_PREFIX_RE.match(line)
        if labelled:
            words = NAME_WORD_RE.findall(labelled.group(1))
            if 1 < len(words) <= 5:
                return " ".join(words)
    for line in lines[:8]:
        if email and email in line:
            continue
        if "@" in line or "http" in line.lower() or PHONE_RE.search(line):
            continue
        if ":" in line and not re.search(r"[\u0600-\u06FF]", line):
            continue
        if title_like(line) or heading_name(line):
            continue
        words = NAME_WORD_RE.findall(line)
        if not 1 < len(words) <= 5:
            continue
        if len(line) > 50:
            continue
        # The line should mostly be the name, not a sentence.
        if len(" ".join(words)) < len(re.sub(r"[\s|/,·•\-–—]+", " ", line).strip()) * 0.7:
            continue
        return " ".join(words)
    return ""


def extract_phone(text: str) -> str:
    for match in PHONE_RE.finditer(text.translate(LOCAL_DIGITS)):
        phone = match.group(0).strip()
        digits = re.sub(r"\D", "", phone)
        if len(digits) < 8 or len(digits) > 15:
            continue
        # Date ranges such as "2018 - 2021" look like numbers too.
        if len(YEAR_RE.findall(phone)) >= 2:
            continue
        return phone
    return ""


def extract_location(lines: list[str]) -> str:
    header = lines[:20]
    for line in header:
        match = LOCATION_PREFIX_RE.match(line)
        if match:
            return clean_location(match.group(1))
    for line in header:
        persian = PERSIAN_PLACE_RE.search(line)
        if persian:
            return clean_location(f"{persian.group(1)}، {persian.group(2)}")
    for line in header:
        found = PLACE_RE.search(line)
        if found and looks_like_place(found.group(1)):
            return clean_location(found.group(1))
    for line in header:
        place = location_from_hints(line)
        if place:
            return place
    return ""


def looks_like_place(value: str) -> bool:
    lowered = value.lower()
    return any(hint.lower() in lowered for hint in COUNTRY_HINTS) or "," in value


def location_from_hints(line: str) -> str:
    if title_like(line) or heading_name(line):
        return ""
    # Contact rows often look like: email | phone | Tehran, Iran
    parts = re.split(r"\s*[|·•/]\s*", line)
    candidates = parts if len(parts) > 1 else [line]
    for part in candidates:
        part = part.strip()
        if not part or "@" in part or "http" in part.lower() or PHONE_RE.search(part):
            continue
        found = PLACE_RE.search(part)
        if found and looks_like_place(found.group(1)):
            return clean_location(found.group(1))
        persian = PERSIAN_PLACE_RE.search(part)
        if persian:
            return clean_location(f"{persian.group(1)}، {persian.group(2)}")
        hits = [hint for hint in COUNTRY_HINTS if re.search(rf"(?<!\w){re.escape(hint)}(?!\w)", part, re.I)]
        if hits:
            return clean_location(part[:80])
    return ""


def clean_location(value: str) -> str:
    value = re.sub(r"\s+", " ", value.replace("\u200c", " ")).strip(" -|·•,،")
    return value[:80]


def first_match(pattern: re.Pattern, text: str) -> str:
    match = pattern.search(text)
    return match.group(0).strip() if match else ""
