import unittest
from pathlib import Path

from app import app
from matcher.cv_parser import parse_cv
from matcher.job_sources import (
    html_to_text,
    parse_eestekhdam_jobs,
    parse_irantalent_html,
    parse_jobinja_html,
    parse_jobvision_payload,
    parse_kardix_jobs,
    parse_quera_html,
)
from matcher.linkedin_search import adapt_job_result, fetch_linkedin_jobs, matches_keyword, search_linkedin
from matcher.post_offers import adapt_web_result, fetch_web_posts, is_job_offer, linkedin_post_search_url, search_posts
from matcher.scorer import contains_term, linkedin_search_url, other_stack, score_and_rank, title_points

SAMPLE = Path(__file__).with_name("sample_cv.txt").read_text(encoding="utf-8")


class MatcherTests(unittest.TestCase):
    def test_parse_sample_cv(self):
        profile = parse_cv(SAMPLE)
        self.assertEqual(profile["name"], "Sara Nouri")
        self.assertEqual(profile["email"], "sara.nouri@example.com")
        self.assertIn("Tehran", profile["location"])
        for skill in ("Python", "SQL", "Excel", "Tableau", "Power BI"):
            self.assertIn(skill, profile["skills"])
        self.assertTrue(any("Data Analyst" in title for title in profile["target_titles"]))

    def test_frontend_cv_shape(self):
        text = """
JANE DOE
Frontend Developer
jane.doe@example.com | +1 202 555 0147 | Lisbon, Portugal | LinkedIn | GitHub
PROFESSIONAL SUMMARY
Frontend Developer specializing in React.js and TypeScript for data-heavy dashboards.
TECHNICAL SKILLS
Languages: JavaScript, TypeScript, HTML5, CSS3, Python (Beginner), C++ (Beginner)
Technologies: React.js, Next.js, Node.js, Tailwind CSS, REST APIs, Git
WORK EXPERIENCES
Northwind 01/2024 - Present
Frontend Developer (React.js)
Link Studio 03/2023 - 12/2023
Full-Stack Developer (Next.js / Node.js), Part-time
EDUCATION
State University 2020 - 2024
"""
        profile = parse_cv(text)
        self.assertEqual(profile["name"], "Jane Doe")
        self.assertEqual(profile["location"], "Lisbon, Portugal")
        for skill in ("JavaScript", "TypeScript", "HTML", "CSS", "React", "Next.js", "Node.js", "Tailwind CSS", "Git"):
            self.assertIn(skill, profile["skills"])
        self.assertNotIn("Python", profile["skills"])
        self.assertNotIn("C++", profile["skills"])
        self.assertNotIn("WORK EXPERIENCES", profile["skills"])
        self.assertGreaterEqual(title_points(profile["target_titles"], "Frontend Engineer"), 22)
        self.assertTrue(other_stack("Senior .NET Full-stack Developer", profile["skills"]))
        self.assertFalse(other_stack("Senior React Full-stack Developer", profile["skills"]))
        self.assertTrue(any(title == "Frontend Developer" for title in profile["target_titles"]))
        self.assertTrue(any(title == "Full-Stack Developer" for title in profile["target_titles"]))

    def test_parse_persian_and_alternate_cv_layouts(self):
        persian = """
علی رضایی
توسعه‌دهنده فرانت‌اند
ali.rezaei@example.com
+98 912 111 2233
تهران، ایران

درباره من
توسعه‌دهنده فرانت‌اند با تجربه React و TypeScript.

مهارت‌ها
React، Next.js، TypeScript، HTML، CSS، Git

سوابق شغلی
توسعه‌دهنده فرانت‌اند
شرکت نمونه | تهران
۱۴۰۲ - اکنون

تحصیلات
مهندسی کامپیوتر
"""
        profile = parse_cv(persian)
        self.assertEqual(profile["name"], "علی رضایی")
        self.assertEqual(profile["email"], "ali.rezaei@example.com")
        self.assertIn("تهران", profile["location"])
        for skill in ("React", "Next.js", "TypeScript", "HTML", "CSS", "Git"):
            self.assertIn(skill, profile["skills"])
        self.assertTrue(any("فرانت" in title for title in profile["target_titles"]))
        self.assertGreaterEqual(title_points(profile["target_titles"], "Frontend Developer"), 22)

        euro = """
Maria Santos
Based in Berlin, Germany
maria.santos@example.com · +49 30 123456 · linkedin.com/in/mariasantos
01 Profile
Backend engineer focused on APIs and data pipelines.
02 Key Skills
Python · Django · PostgreSQL · Docker · AWS
03 Employment History
DataCorp — Backend Engineer
2022 - Present
Built payment services in Python.
"""
        euro_profile = parse_cv(euro)
        self.assertEqual(euro_profile["name"], "Maria Santos")
        self.assertIn("Berlin", euro_profile["location"])
        for skill in ("Python", "Django", "PostgreSQL", "Docker", "AWS"):
            self.assertIn(skill, euro_profile["skills"])
        self.assertTrue(any("Backend Engineer" in title for title in euro_profile["target_titles"]))

        oneline = """
Sam Karimi
Frontend Developer | Remote | sam.karimi@example.com | +1-415-555-0199 | San Francisco, USA
Skills: React, TypeScript, CSS, Figma
Experience
Acme Labs | Frontend Developer | 2023 - Present
"""
        one = parse_cv(oneline)
        self.assertEqual(one["name"], "Sam Karimi")
        self.assertIn("San Francisco", one["location"])
        self.assertIn("React", one["skills"])
        self.assertTrue(any(title == "Frontend Developer" for title in one["target_titles"]))

    def test_two_column_pdf_reads_one_column_at_a_time(self):
        import pymupdf

        from matcher.cv_parser import read_upload

        document = pymupdf.open()
        page = document.new_page(width=595, height=842)
        page.insert_text((40, 60), "LEILA AHMADI", fontsize=22)
        page.insert_text((40, 80), "Product Designer", fontsize=12)
        left = ["CONTACT", "leila.ahmadi@example.com", "0912 345 6789", "Shiraz, Iran", "",
                "MY SKILLS", "Figma", "Prototyping", "User Research 90%", "", "LANGUAGES", "English - Fluent"]
        right = ["ABOUT ME", "Product designer who turns research into clear interfaces.", "",
                 "WORK HISTORY", "Senior Product Designer", "Pay Co, Tehran 2021 - Present", "",
                 "UI Designer", "Studio Nine 2018-2021"]
        for column, x in ((left, 40), (right, 240)):
            for row, line in enumerate(column):
                page.insert_text((x, 130 + row * 16), line, fontsize=10)
        profile = parse_cv(read_upload("cv.pdf", document.tobytes()))
        self.assertEqual(profile["name"], "Leila Ahmadi")
        self.assertEqual(profile["phone"], "0912 345 6789")
        self.assertEqual(profile["location"], "Shiraz, Iran")
        self.assertEqual(profile["skills"][:3], ["Figma", "Prototyping", "User Research"])
        self.assertNotIn("English", profile["skills"])
        self.assertEqual(profile["target_titles"], ["Product Designer", "Senior Product Designer", "UI Designer"])
        self.assertIn("clear interfaces", profile["summary"])

    def test_docx_header_and_text_boxes_are_read_once(self):
        import io
        import zipfile

        from matcher.cv_parser import read_upload

        w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        mc = 'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'

        def p(text):
            return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"

        box = p("Core Competencies") + p("Accounting, IFRS, QuickBooks")
        body = (
            p("Professional Summary") + p("Accountant with eight years of audit work for manufacturers.")
            + "<w:p><w:r><mc:AlternateContent><mc:Choice><w:txbxContent>" + box
            + "</w:txbxContent></mc:Choice><mc:Fallback><w:txbxContent>" + box
            + "</w:txbxContent></mc:Fallback></mc:AlternateContent></w:r></w:p>"
            + p("Employment History") + p("Senior Accountant") + p("Atlas Steel 2019 - Present")
        )
        header = p("Reza Karimi") + p("Accountant") + p("reza.k@example.com | 09121234567 | Isfahan, Iran")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("word/document.xml", f"<w:document {w} {mc}><w:body>{body}</w:body></w:document>")
            archive.writestr("word/header1.xml", f"<w:hdr {w}>{header}</w:hdr>")
        text = read_upload("cv.docx", buffer.getvalue())
        self.assertEqual(text.count("Core Competencies"), 1)
        profile = parse_cv(text)
        self.assertEqual(profile["name"], "Reza Karimi")
        self.assertEqual(profile["phone"], "09121234567")
        self.assertEqual(profile["location"], "Isfahan, Iran")
        self.assertEqual(profile["skills"], ["Accounting", "IFRS", "QuickBooks"])
        self.assertEqual(profile["target_titles"], ["Accountant", "Senior Accountant"])

    def test_spaced_headings_labels_and_ratings(self):
        profile = parse_cv(
            """
Name: John Peter Smith
Mechanical Engineer
Phone: +44 7700 900123   Email: john.smith@example.com
London, United Kingdom
P R O F I L E
Mechanical engineer with ten years in HVAC design.
S K I L L S
AutoCAD ★★★★★
SolidWorks - Advanced
W O R K   E X P E R I E N C E
Design Engineer - Arup
2016 - 2024
"""
        )
        self.assertEqual(profile["name"], "John Peter Smith")
        self.assertEqual(profile["phone"], "+44 7700 900123")
        self.assertEqual(profile["skills"], ["AutoCAD", "SolidWorks"])
        self.assertEqual(profile["target_titles"], ["Mechanical Engineer", "Design Engineer"])
        self.assertEqual(profile["summary"], "Mechanical engineer with ten years in HVAC design.")

    def test_ai_reader_fills_profile_and_falls_back(self):
        import json
        import os
        from unittest import mock

        import requests

        from matcher.cv_parser import read_cv

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "", "GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_MODEL": ""}):
            profile, reader = read_cv(SAMPLE)
        self.assertEqual(reader, {"reader": "rules", "error": "", "model": ""})
        self.assertEqual(profile["name"], "Sara Nouri")

        answer = {
            "name": "Sara Nouri",
            "email": "not an email",
            "phone": "+98 912 000 0000",
            "location": "Tehran, Iran",
            "linkedin": "linkedin.com/in/saranouri",
            "summary": "Data analyst.",
            "skills": ["python", "Power BI", "dbt", "Python"],
            "target_titles": ["Senior Data Analyst", "Data Analyst"],
        }
        reply = mock.Mock()
        reply.json.return_value = {"choices": [{"message": {"content": "```json\n" + json.dumps(answer) + "\n```"}}]}
        with mock.patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test",
                "GEMINI_API_KEY": "",
                "GROQ_API_KEY": "",
                "OLLAMA_MODEL": "",
                "CV_AI_MODEL": "",
                "OPENAI_BASE_URL": "",
            },
        ), mock.patch("matcher.cv_ai.requests.post", return_value=reply) as call:
            profile, reader = read_cv(SAMPLE)
        self.assertEqual(reader["reader"], "ai")
        self.assertIn("OpenAI/", reader["model"])
        self.assertIn("/chat/completions", call.call_args.args[0])
        self.assertEqual(profile["email"], "sara.nouri@example.com")
        self.assertEqual(profile["linkedin"], "https://linkedin.com/in/saranouri")
        self.assertEqual(profile["skills"], ["Python", "Power BI", "dbt"])
        self.assertEqual(profile["target_titles"], ["Senior Data Analyst", "Data Analyst"])

        from matcher.cv_ai import providers, settings

        router = {
            "OPENAI_API_KEY": "test",
            "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
            "CV_AI_ALLOW_PAID": "",
            "GEMINI_API_KEY": "",
            "GROQ_API_KEY": "",
            "OLLAMA_MODEL": "",
        }
        with mock.patch.dict(os.environ, {**router, "CV_AI_MODEL": ""}):
            models = settings()["model"].split(",")
            self.assertTrue(all(name.endswith(":free") or name == "openrouter/free" for name in models))
            self.assertIn("openrouter/free", models)
        with mock.patch.dict(os.environ, {**router, "CV_AI_MODEL": "gpt-4o-mini,google/gemma-4-31b-it:free"}):
            self.assertEqual(settings()["model"], "google/gemma-4-31b-it:free")
        with mock.patch.dict(os.environ, {**router, "CV_AI_MODEL": "openai/gpt-4o-mini"}):
            self.assertIsNone(settings())

        busy = mock.Mock(status_code=429, text="rate limit")
        busy.raise_for_status.side_effect = requests.HTTPError("429")
        ok = mock.Mock()
        ok.status_code = 200
        ok.json.return_value = {"choices": [{"message": {"content": json.dumps(answer)}}]}
        env = {
            "OPENAI_API_KEY": "or-key",
            "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
            "CV_AI_MODEL": "google/gemma-4-31b-it:free,nvidia/nemotron-3-super-120b-a12b:free",
            "GEMINI_API_KEY": "gem-key",
            "CV_AI_GEMINI_MODELS": "gemini-2.5-flash",
            "GROQ_API_KEY": "",
            "OLLAMA_MODEL": "",
            "CV_AI_ALLOW_PAID": "",
        }
        with mock.patch.dict(os.environ, env):
            self.assertEqual([item["name"] for item in providers()], ["OpenRouter", "Gemini"])
        with mock.patch.dict(os.environ, env), mock.patch(
            "matcher.cv_ai.requests.post", side_effect=[busy, ok]
        ) as call:
            profile, reader = read_cv(SAMPLE)
        self.assertEqual(reader["reader"], "ai")
        self.assertEqual(reader["model"], "OpenRouter/nvidia/nemotron-3-super-120b-a12b:free")
        self.assertEqual(call.call_count, 2)
        self.assertEqual(profile["skills"], ["Python", "Power BI", "dbt"])

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "", "GEMINI_API_KEY": "test", "GROQ_API_KEY": "", "OLLAMA_MODEL": "", "CV_AI_MODEL": ""}), mock.patch(
            "matcher.cv_ai.requests.post", side_effect=requests.ConnectionError("blocked")
        ):
            profile, reader = read_cv(SAMPLE)
        self.assertEqual(reader["reader"], "rules")
        self.assertIn("could not be reached", reader["error"])
        self.assertEqual(profile["name"], "Sara Nouri")

    def test_scoring_keeps_fit_and_drops_other_city(self):
        profile = parse_cv(SAMPLE)
        analyst = {
            "source": "Example",
            "title": "Senior Data Analyst",
            "company": "Northwind",
            "location": "Remote",
            "remote": True,
            "url": "https://example.com/jobs/analyst",
            "description": "We need Python, SQL, Tableau, Power BI, and statistics experience.",
            "tags": ["data"],
            "published": "2026-01-01",
            "salary": "",
        }
        dentist = {
            "source": "Example",
            "title": "Dentist",
            "company": "City Clinic",
            "location": "Berlin, Germany",
            "remote": False,
            "url": "https://example.com/jobs/dentist",
            "description": "Patient care in a dental clinic.",
            "tags": [],
            "published": "",
            "salary": "",
        }
        ranked = score_and_rank(profile, [analyst, dentist])
        self.assertEqual(len(ranked), 1)
        self.assertGreaterEqual(ranked[0]["score"], 70)
        self.assertIn("Northwind", ranked[0]["cover_letter"])
        self.assertIn("linkedin.com/jobs/search", ranked[0]["linkedin_search_url"])

    def test_foreign_regions_keep_germany_and_drop_other_countries(self):
        profile = parse_cv(SAMPLE)
        profile["target_titles"] = ["Frontend Developer"]
        profile["skills"] = ["React", "TypeScript", "JavaScript"]
        profile["target_regions"] = ["Germany", "Austria", "Europe", "United States", "Canada"]
        berlin = {
            "source": "Example",
            "title": "Frontend Developer",
            "company": "Berlin Works",
            "location": "Berlin, Germany",
            "remote": False,
            "url": "https://example.com/jobs/berlin",
            "description": "React and TypeScript for a product team.",
            "tags": [],
            "published": "",
            "salary": "",
        }
        cairo = {
            "source": "Example",
            "title": "Frontend Developer",
            "company": "Cairo Labs",
            "location": "Cairo, Egypt",
            "remote": False,
            "url": "https://example.com/jobs/cairo",
            "description": "React and TypeScript product work.",
            "tags": [],
            "published": "",
            "salary": "",
        }
        ranked = score_and_rank(profile, [berlin, cairo])
        self.assertEqual([item["company"] for item in ranked], ["Berlin Works"])
        self.assertIn("Germany", ranked[0]["cover_letter"])
        self.assertNotIn("Tehran", ranked[0]["linkedin_search_url"])

    def test_iran_jobs_sort_ahead_of_foreign_jobs(self):
        profile = parse_cv(SAMPLE)
        profile["target_titles"] = ["Frontend Developer"]
        profile["skills"] = ["React", "TypeScript"]
        profile["target_regions"] = ["Germany", "Austria", "Europe", "United States", "Canada"]
        tehran = {
            "source": "Example",
            "title": "Frontend Developer",
            "company": "Tehran Works",
            "location": "Tehran, Iran",
            "remote": False,
            "url": "https://example.com/jobs/tehran",
            "description": "React and TypeScript.",
            "tags": [],
            "published": "",
            "salary": "",
        }
        berlin = {
            "source": "Example",
            "title": "Frontend Developer",
            "company": "Berlin Works",
            "location": "Berlin, Germany",
            "remote": False,
            "url": "https://example.com/jobs/berlin",
            "description": "React and TypeScript for a larger product team with extra overlap.",
            "tags": ["React"],
            "published": "",
            "salary": "",
        }
        ranked = score_and_rank(profile, [berlin, tehran])
        self.assertEqual([item["company"] for item in ranked], ["Tehran Works", "Berlin Works"])
        self.assertIn("available for this role in Iran", ranked[0]["cover_letter"])
        self.assertIn("Germany", ranked[1]["cover_letter"])

    def test_all_countries_keeps_every_listing_and_home_country_first(self):
        profile = parse_cv(SAMPLE)
        profile["target_titles"] = ["Frontend Developer"]
        profile["skills"] = ["React", "TypeScript"]
        profile["all_countries"] = True
        profile["target_regions"] = []
        cairo = {
            "source": "Example",
            "title": "Frontend Developer",
            "company": "Cairo Labs",
            "location": "Cairo, Egypt",
            "remote": False,
            "url": "https://example.com/jobs/cairo",
            "description": "React and TypeScript product work.",
            "tags": [],
            "published": "",
            "salary": "",
        }
        tehran = {
            "source": "Example",
            "title": "Frontend Developer",
            "company": "Tehran Works",
            "location": "Tehran, Iran",
            "remote": False,
            "url": "https://example.com/jobs/tehran",
            "description": "React and TypeScript.",
            "tags": [],
            "published": "",
            "salary": "",
        }
        ranked = score_and_rank(profile, [cairo, tehran])
        self.assertEqual([item["company"] for item in ranked], ["Tehran Works", "Cairo Labs"])
        self.assertIn("any country", ranked[1]["cover_letter"])

    def test_jobinja_card_is_an_iran_frontend_role(self):
        page = """
        <a class="c-jobListView__titleLink" href="https://jobinja.ir/companies/hub/jobs/abc/role?ref=1">
          برنامه&zwnj;نویس فرانت اند (Front-End)
        </a>
        <i class="c-icon--construction"></i><span>Hub | هاب</span>
        <i class="c-icon--place"></i><span>تهران، تهران</span>
        """
        jobs = parse_jobinja_html(page)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["location"], "Tehran, Iran")
        self.assertEqual(jobs[0]["company"], "Hub | هاب")
        self.assertGreaterEqual(title_points(["Frontend Developer"], jobs[0]["title"]), 22)

    def test_iran_board_cards_keep_tehran_and_frontend_titles(self):
        vision = parse_jobvision_payload(
            {
                "data": {
                    "jobPosts": [
                        {
                            "id": 1559271,
                            "title": "Front-End Developer",
                            "activationTime": "2026-10-01T08:00:00Z",
                            "properties": {"isRemote": False, "salaryCanBeShown": False},
                            "company": {"nameEn": "Hamrah Tel", "nameFa": "تلسا"},
                            "location": {"city": {"titleEn": "Tehran"}, "province": {"titleFa": "تهران"}},
                        }
                    ]
                }
            }
        )
        self.assertEqual(vision[0]["source"], "Jobvision")
        self.assertEqual(vision[0]["location"], "Tehran, Iran")
        self.assertEqual(vision[0]["url"], "https://jobvision.ir/jobs/1559271")
        self.assertGreaterEqual(title_points(["Frontend Developer"], vision[0]["title"]), 22)

        quera_page = """
        <script id="__NEXT_DATA__" type="application/json">
        {"props":{"pageProps":{"jobs":{"edges":[{"node":{"pk":"vr6xm","title":"Frontend Developer","open":true,
        "offers_remote":false,"publish_time":"2026-09-28T11:21:44+00:00","salary":null,
        "company":{"name":"شرکت نمونه"},"city":{"name":"تهران"},
        "jobtechnology_set":[{"technology":{"name":"React"}}]}}]}}}}
        </script>
        """
        quera = parse_quera_html(quera_page)
        self.assertEqual(quera[0]["url"], "https://quera.org/magnet/jobs/vr6xm")
        self.assertEqual(quera[0]["location"], "Tehran, Iran")
        self.assertIn("React", quera[0]["description"])

        talent_page = """
        <script id="ng-state" type="application/json">
        {"serverSideSearchResult":{"data":{"data":[{"id":181512,"title":"Frontend Developer",
        "title_farsi":"فرانت‌اند","slug":"frontend-developer","lived_at":"2026-10-02",
        "employer":{"name":"Viuna"},"location":{"title":"Tehran"},"role_description":"<p>React</p>"}]}}}
        </script>
        """
        talent = parse_irantalent_html(talent_page)
        self.assertEqual(talent[0]["url"], "https://www.irantalent.com/job/frontend-developer/181512")
        self.assertEqual(talent[0]["company"], "Viuna")
        self.assertEqual(talent[0]["location"], "Tehran, Iran")

        kardix = parse_kardix_jobs(
            [
                {
                    "id": 6019904,
                    "title": "توسعه دهنده فرانت اند",
                    "company": {"title": "ویونا"},
                    "city": {"title": "تهران"},
                    "location": {"title": "تهران"},
                    "employment_type": "full_time",
                    "published_at": "2026-10-10T13:10:34+03:30",
                    "salary": "توافقی",
                    "conditions": "<p>React و Next.js</p>",
                }
            ]
        )
        self.assertEqual(kardix[0]["url"], "https://kardix.com/jobs/6019904")
        self.assertEqual(kardix[0]["location"], "Tehran, Iran")
        self.assertGreaterEqual(title_points(["Frontend Developer"], kardix[0]["title"]), 22)

        estekhdam = parse_eestekhdam_jobs(
            [
                {
                    "short_title": "Frontend Developer",
                    "title": "استخدام Frontend Developer در تهران",
                    "brand_name": "آتی هوش",
                    "url": "/kabc-frontend",
                    "provinces": ["تهران"],
                    "contract": ["تمام وقت"],
                    "technologies": ["React"],
                    "salary": "توافقی",
                    "expired": False,
                }
            ]
        )
        self.assertEqual(estekhdam[0]["source"], "e-Estekhdam")
        self.assertEqual(estekhdam[0]["location"], "Tehran, Iran")
        self.assertEqual(estekhdam[0]["url"], "https://www.e-estekhdam.com/kabc-frontend")
        self.assertIn("React", estekhdam[0]["description"])
        self.assertGreaterEqual(title_points(["Back-end developer"], "Back-End Developer (Java)"), 22)
        self.assertGreaterEqual(title_points(["Back-end developer"], "برنامه نویس بک اند"), 22)

    def test_linkedin_post_offer_detection(self):
        offer = "استخدام Frontend Developer در تهران. React و TypeScript. ارسال رزومه."
        seeker = "جویای کار هستم و open to work به عنوان طراح."
        self.assertTrue(is_job_offer(offer, ["Frontend Developer"]))
        self.assertFalse(is_job_offer(seeker, ["Frontend Developer"]))
        arabic = "React 19 hooks من ضمن ال hooks دي --useFormStatus من ضمن الاخطاء استخدام"
        self.assertFalse(is_job_offer(arabic, ["React Developer"]))
        url = linkedin_post_search_url("استخدام Frontend Developer تهران")
        self.assertIn("linkedin.com/search/results/content/", url)
        self.assertIn("date_posted", url)

    def test_web_search_results_become_posts(self):
        item = {
            "title": "استخدام <strong>Frontend Developer</strong> | LinkedIn",
            "url": "https://ir.linkedin.com/posts/acme-labs_hiring-activity-7512345678901234567-AbCd?trk=public",
            "content": "React و TypeScript، حضوری در تهران. ارسال رزومه به jobs@acme.ir",
            "published_date": "Sun, 11 Oct 2026 08:00:00 GMT",
        }
        post = adapt_web_result(item, "Iran")
        self.assertEqual(post["url"], "https://www.linkedin.com/posts/acme-labs_hiring-activity-7512345678901234567-AbCd")
        self.assertEqual(post["title"], "استخدام Frontend Developer")
        self.assertEqual(post["company"], "Posted by Acme Labs")
        self.assertEqual(post["location"], "Tehran, Iran")
        self.assertEqual(post["published"], "2026-10-11")
        self.assertEqual(post["apply_email"], "jobs@acme.ir")
        self.assertIsNone(adapt_web_result({**item, "url": "https://www.linkedin.com/jobs/view/123"}, "Iran"))
        self.assertIsNone(adapt_web_result({**item, "url": "https://linkedin.com.evil.io/posts/x"}, "Iran"))
        posts, _ = search_posts({"target_titles": ["Frontend Developer"]}, [post])
        self.assertIn(post["url"], [found["url"] for found in posts])
        undated = adapt_web_result(
            {
                "title": "Sara Ahmadi's Post",
                "url": "https://www.linkedin.com/posts/fara-ro_x-activity-7512122623011516416-3Nix",
                "content": "استخدام فرانت اند React در تهران",
            },
            "Iran",
        )
        self.assertEqual(undated["published"], "2026-10-03")
        self.assertEqual(undated["title"], "استخدام فرانت اند React در تهران")

    def test_web_search_needs_key(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": ""}):
            posts, report, _searched = fetch_web_posts({"target_titles": ["Frontend Developer"]})
        self.assertEqual(posts, [])
        self.assertFalse(report["ok"])

    def test_web_search_skips_recent_queries(self):
        import os
        import time
        from unittest import mock

        profile = {"target_titles": ["Frontend Developer"], "location": "Tehran, Iran"}
        reply = mock.Mock()
        reply.json.return_value = {"results": []}
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test"}), mock.patch("matcher.post_offers.requests.post", return_value=reply) as call:
            _posts, report, searched = fetch_web_posts(profile, {})
            self.assertEqual(call.call_count, 1)
            self.assertTrue(report["ok"])
            fetch_web_posts(profile, searched)
            self.assertEqual(call.call_count, 1)
            stale = {key: time.time() - 7 * 3600 for key in searched}
            fetch_web_posts(profile, stale)
            self.assertEqual(call.call_count, 2)

    def test_word_boundaries_and_html(self):
        self.assertTrue(contains_term("Senior Data Analyst", "data analyst"))
        self.assertFalse(contains_term("excellent work", "excel"))
        self.assertIn("Python", html_to_text("<p>Need <b>Python</b></p><script>nope</script>"))
        self.assertNotIn("nope", html_to_text("<p>Need <b>Python</b></p><script>nope</script>"))

    def test_linkedin_url_uses_role_and_easy_apply(self):
        url = linkedin_search_url("Data analyst", "Tehran, Iran", easy_apply=True, remote_only=True)
        self.assertIn("keywords=Data+analyst", url)
        self.assertIn("f_AL=true", url)
        self.assertIn("f_WT=2", url)
        self.assertIn("Tehran", url)

    def test_pages_and_parse_endpoint(self):
        import app as app_module
        import os
        from tempfile import TemporaryDirectory
        from unittest import mock

        with TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"OPENAI_API_KEY": "", "GEMINI_API_KEY": ""}):
            posts_path = app_module.POSTS_PATH
            feed_url = app_module.FEED_URL
            app_module.POSTS_PATH = Path(folder) / "linkedin_posts.json"
            app_module.FEED_URL = ""
            try:
                client = app.test_client()
                home = client.get("/")
                self.assertEqual(home.status_code, 200)
                self.assertIn(b"Find roles that fit your CV", home.data)
                self.assertIn(b"Job offers in LinkedIn posts", home.data)
                self.assertIn(b'aria-label="Match pages"', home.data)
                self.assertIn(b'aria-label="Post pages"', home.data)
                self.assertIn(b'aria-label="Saved role pages"', home.data)
                self.assertIn(b'aria-label="Sections"', home.data)
                self.assertIn(b'data-pane="profile"', home.data)
                parsed = client.post("/api/parse", json={"text": SAMPLE})
                self.assertEqual(parsed.status_code, 200)
                body = parsed.get_json()["profile"]
                self.assertEqual(body["name"], "Sara Nouri")
                self.assertEqual(parsed.get_json()["reader"], "rules")
                missing = client.post("/api/search", json={"target_titles": [], "skills": []})
                self.assertEqual(missing.status_code, 400)
                blocked = client.post(
                    "/api/parse",
                    json={"text": SAMPLE},
                    headers={"Origin": "https://example.evil"},
                )
                self.assertEqual(blocked.status_code, 403)
                public = client.post(
                    "/api/parse",
                    json={"text": SAMPLE},
                    headers={"Origin": "http://briefrole.ir", "Host": "briefrole.ir"},
                )
                self.assertEqual(public.status_code, 200)
                self.assertEqual(list(Path(folder).iterdir()), [])
                other_visitor = app.test_client()
                self.assertEqual(other_visitor.get("/api/profile").status_code, 404)
                self.assertEqual(other_visitor.get("/api/applications").status_code, 404)
                posts = other_visitor.post("/api/posts", json={})
                self.assertEqual(posts.status_code, 200)
                self.assertNotIn(b"Sara Nouri", posts.data)
            finally:
                app_module.POSTS_PATH = posts_path
                app_module.FEED_URL = feed_url

    def test_post_feed_is_cleaned_and_checked_hourly(self):
        import app as app_module
        from tempfile import TemporaryDirectory
        from unittest import mock

        good = {
            "title": "استخدام React Developer",
            "company": "Acme",
            "location": "Tehran, Iran",
            "url": "https://ir.linkedin.com/posts/acme_hiring-activity-1?trk=x",
            "published": "2026-10-12",
            "snippet": "React و TypeScript. ارسال رزومه به jobs@acme.ir",
            "apply_email": "not-an-email\nBcc:x@y.z",
        }
        bad = {**good, "url": "javascript:alert(1)"}
        reply = mock.Mock()
        reply.json.return_value = {"posts": [good, bad, "junk"]}
        with TemporaryDirectory() as folder:
            saved = (app_module.POSTS_PATH, app_module.FEED_CHECK_PATH, app_module.FEED_URL)
            app_module.POSTS_PATH = Path(folder) / "linkedin_posts.json"
            app_module.FEED_CHECK_PATH = Path(folder) / "feed_checked.json"
            app_module.FEED_URL = "https://example.test/feed.json"
            try:
                with mock.patch("matcher.post_offers.requests.get", return_value=reply) as call:
                    stored, report = app_module.refresh_posts({})
                    self.assertTrue(report["ok"])
                    self.assertEqual(len(stored), 1)
                    self.assertEqual(stored[0]["url"], "https://www.linkedin.com/posts/acme_hiring-activity-1")
                    self.assertEqual(stored[0]["apply_email"], "jobs@acme.ir")
                    again, second_report = app_module.refresh_posts({})
                    self.assertIsNone(second_report)
                    self.assertEqual(again, stored)
                    self.assertEqual(call.call_count, 1)
            finally:
                app_module.POSTS_PATH, app_module.FEED_CHECK_PATH, app_module.FEED_URL = saved

    def test_linkedin_job_results_and_keyword_match(self):
        item = {
            "title": "Snapp hiring Senior <b>Frontend</b> Developer in Tehran, Tehran Province, Iran | LinkedIn",
            "url": "https://ir.linkedin.com/jobs/view/senior-frontend-developer-at-snapp-4012345678?trk=public",
            "content": "React, TypeScript, and Next.js. Send a CV to jobs@snapp.ir",
            "published_date": "2026-10-10",
        }
        job = adapt_job_result(item)
        self.assertEqual(job["url"], "https://www.linkedin.com/jobs/view/senior-frontend-developer-at-snapp-4012345678")
        self.assertEqual(job["title"], "Senior Frontend Developer")
        self.assertEqual(job["company"], "Snapp")
        self.assertEqual(job["location"], "Tehran, Tehran Province, Iran")
        self.assertEqual(job["published"], "2026-10-10")
        self.assertEqual(job["apply_email"], "jobs@snapp.ir")
        self.assertIsNone(adapt_job_result({**item, "url": "https://www.linkedin.com/posts/x-activity-1"}))
        self.assertIsNone(adapt_job_result({**item, "url": "https://linkedin.com.evil.io/jobs/view/1"}))

        base = "https://www.linkedin.com/jobs/view/"
        shapes = [
            ("React JS Developer at Programmers.io — Dallas, TX - Jobs", "react-js-developer-at-programmers-io-4471918921",
             ("React JS Developer", "Programmers.io", "Dallas, TX")),
            ("Signature IT World Inc hiring React Developer in Sunnyvale ...", "4465221243",
             ("React Developer", "Signature IT World Inc", "Sunnyvale")),
            ("React Developer (US)", "react-developer-us-at-edgeq-technologies-private-limited-4477807638",
             ("React Developer (US)", "Edgeq Technologies Private Limited", "")),
            ("Django React Developer - Remote Work at BairesDev", "django-react-developer-remote-work-at-bairesdev-4474993455",
             ("Django React Developer - Remote Work", "BairesDev", "Remote")),
            ("React Developer - Bright Vision Technologies", "react-developer-at-bright-vision-technologies-4476364632",
             ("React Developer", "Bright Vision Technologies", "")),
            ("React Developer - Remote Work", "react-developer-remote-work-at-indi-staffing-services-4476776933",
             ("React Developer - Remote Work", "Indi Staffing Services", "Remote")),
            ("Frontend Engineer - Acme Labs", "4465221299", ("Frontend Engineer", "Acme Labs", "")),
        ]
        for title, path, expected in shapes:
            parsed = adapt_job_result({"title": title, "url": base + path, "content": "React and TypeScript."})
            self.assertEqual((parsed["title"], parsed["company"], parsed["location"]), expected, title)
        self.assertTrue(matches_keyword("Senior Front-End Developer, React", "frontend react"))
        self.assertTrue(matches_keyword("استخدام فرانت‌اند کار", "فرانت"))
        self.assertFalse(matches_keyword("Senior Backend Developer", "frontend"))

    def test_linkedin_search_finds_jobs_and_posts_for_a_keyword(self):
        import os
        from unittest import mock

        job = {
            "title": "Acme hiring React Developer in Tehran, Iran | LinkedIn",
            "url": "https://www.linkedin.com/jobs/view/react-developer-at-acme-4011111111",
            "content": "React and TypeScript.",
        }
        post = {
            "title": "استخدام React Developer | LinkedIn",
            "url": "https://www.linkedin.com/posts/acme_hiring-activity-7512345678901234567-AbCd",
            "content": "React در تهران. ارسال رزومه به jobs@acme.ir",
        }
        replies = [mock.Mock(), mock.Mock()]
        replies[0].json.return_value = {"results": [job, {**job, "url": job["url"] + "?trk=x"}]}
        replies[1].json.return_value = {"results": [post]}
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test"}), mock.patch(
            "matcher.linkedin_search.requests.post", side_effect=replies
        ) as call:
            result = search_linkedin("react", location="Tehran, Iran")
        self.assertEqual(call.call_count, 2)
        self.assertEqual(call.call_args_list[0].kwargs["json"]["include_domains"], ["linkedin.com/jobs/view"])
        self.assertEqual(call.call_args_list[0].kwargs["json"]["query"], "react remote jobs")
        self.assertEqual(result["reports"][0]["name"], "LinkedIn jobs (remote)")
        self.assertEqual(call.call_args_list[1].kwargs["json"]["query"], "استخدام react")
        self.assertEqual([item["title"] for item in result["jobs"]], ["React Developer"])
        self.assertIn(post["url"], [item["url"] for item in result["posts"]])
        self.assertTrue(all(matches_keyword(f"{p['title']} {p['snippet']}", "react") for p in result["posts"]))
        self.assertIn("keywords=react", result["links"]["jobs"])

        with mock.patch("matcher.linkedin_search.requests.post") as call:
            offline = search_linkedin("react", offline=True)
        call.assert_not_called()
        self.assertEqual(offline["jobs"], [])
        self.assertTrue(offline["posts"])

    def test_app_search_includes_linkedin_jobs_from_feed_or_tavily(self):
        import app as app_module
        import os
        from tempfile import TemporaryDirectory
        from unittest import mock

        item = {
            "title": "Acme hiring Frontend Developer in Tehran, Iran | LinkedIn",
            "url": "https://www.linkedin.com/jobs/view/frontend-developer-at-acme-4099999999",
            "content": "React and TypeScript in Tehran.",
            "published_date": "2026-10-12",
        }
        feed_job = {
            "title": "Frontend <b>Developer</b>",
            "company": "Beta",
            "location": "Tehran, Iran",
            "url": "https://ir.linkedin.com/jobs/view/frontend-developer-at-beta-4088888888?trk=x",
            "published": "2026-10-11",
            "snippet": "React. Send a CV to jobs@beta.ir",
            "apply_email": "not-an-email\nBcc:x@y.z",
        }
        profile = {
            "name": "Sara Nouri",
            "location": "Tehran, Iran",
            "skills": ["React", "TypeScript"],
            "target_titles": ["Frontend Developer"],
            "target_regions": ["Iran"],
        }
        tavily = mock.Mock()
        tavily.json.return_value = {"results": [item]}
        feed = mock.Mock()
        feed.json.return_value = {"jobs": [feed_job, {**feed_job, "url": "javascript:alert(1)"}, "junk"]}

        jobs, report = fetch_linkedin_jobs({**profile, "target_titles": []})
        self.assertEqual(jobs, [])
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test"}), mock.patch(
            "matcher.linkedin_search.requests.post", return_value=tavily
        ):
            jobs, report = fetch_linkedin_jobs(profile)
        self.assertTrue(report["ok"])
        self.assertEqual([job["title"] for job in jobs], ["Frontend Developer"])

        saved = (app_module.JOBS_PATH, app_module.JOBS_FEED_CHECK_PATH, app_module.JOBS_FEED_URL)
        with TemporaryDirectory() as folder, mock.patch("app.search_jobs", side_effect=lambda titles: ([], [])), mock.patch(
            "app.refresh_posts", return_value=([], None)
        ):
            app_module.JOBS_PATH = Path(folder) / "linkedin_jobs.json"
            app_module.JOBS_FEED_CHECK_PATH = Path(folder) / "jobs_feed_checked.json"
            try:
                app_module.JOBS_FEED_URL = "https://example.test/jobs.json"
                with mock.patch("matcher.linkedin_search.requests.get", return_value=feed) as call, mock.patch(
                    "matcher.linkedin_search.requests.post"
                ) as search:
                    first = app.test_client().post("/api/search", json=profile).get_json()
                    second = app.test_client().post("/api/search", json=profile).get_json()
                self.assertEqual(call.call_count, 1)
                search.assert_not_called()
                for payload in (first, second):
                    linkedin = [job for job in payload["jobs"] if job["source"] == "LinkedIn job"]
                    self.assertEqual([job["company"] for job in linkedin], ["Beta"])
                    self.assertEqual(linkedin[0]["url"], "https://www.linkedin.com/jobs/view/frontend-developer-at-beta-4088888888")
                    self.assertEqual(linkedin[0]["apply_email"], "jobs@beta.ir")
                    self.assertIn({"name": "LinkedIn jobs", "ok": True, "count": 1, "error": ""}, payload["sources"])

                app_module.JOBS_FEED_URL = ""
                with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test"}), mock.patch(
                    "matcher.linkedin_search.requests.post", return_value=tavily
                ):
                    payload = app.test_client().post("/api/search", json=profile).get_json()
                companies = {job["company"] for job in payload["jobs"] if job["source"] == "LinkedIn job"}
                self.assertEqual(companies, {"Acme", "Beta"})
            finally:
                app_module.JOBS_PATH, app_module.JOBS_FEED_CHECK_PATH, app_module.JOBS_FEED_URL = saved


    def test_remote_search_runs_workflow_and_saves_results(self):
        import json
        import subprocess
        from tempfile import TemporaryDirectory
        from unittest import mock

        from scripts import search_linkedin as cli

        result = {
            "jobs": [
                {
                    "title": "React Developer",
                    "company": "Acme",
                    "location": "Tehran, Iran",
                    "url": "https://ir.linkedin.com/jobs/view/react-developer-at-acme-4011111111?trk=x",
                    "snippet": "React. Send a CV to jobs@acme.ir",
                },
                {"title": "Bad", "url": "javascript:alert(1)"},
            ],
            "posts": [
                {
                    "title": "استخدام React Developer",
                    "url": "https://www.linkedin.com/posts/acme_hiring-activity-7512345678901234567-AbCd",
                    "snippet": "React در تهران",
                }
            ],
            "reports": [],
            "links": {"jobs": "https://www.linkedin.com/jobs/search/", "posts": "https://www.linkedin.com/search/"},
        }
        calls = []
        polls = iter(["in_progress", "completed"])

        def fake_gh(command, **kwargs):
            args = command[1:]
            calls.append(args)
            output = ""
            if args[:2] == ["workflow", "run"]:
                fake_gh.request_id = next(a.split("=", 1)[1] for a in args if a.startswith("request_id="))
            elif args[:2] == ["run", "list"]:
                output = json.dumps([{"databaseId": 7, "displayTitle": f"LinkedIn search: react [{fake_gh.request_id}]"}])
            elif args[:2] == ["run", "view"]:
                output = json.dumps({"status": next(polls), "conclusion": "success", "url": "https://github.com/x"})
            elif args[:2] == ["run", "download"]:
                folder = Path(args[args.index("-D") + 1])
                (folder / "linkedin_search.json").write_text(json.dumps(result), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, output, "")

        with TemporaryDirectory() as folder, mock.patch("scripts.search_linkedin.subprocess.run", side_effect=fake_gh), mock.patch(
            "scripts.search_linkedin.time.sleep"
        ), mock.patch.object(cli, "DATA_JOBS", Path(folder) / "jobs.json"), mock.patch.object(
            cli, "DATA_POSTS", Path(folder) / "posts.json"
        ), mock.patch("sys.stdout"):
            self.assertEqual(cli.main(["react", "--remote", "--location", "Tehran, Iran"]), 0)
            jobs = json.loads((Path(folder) / "jobs.json").read_text(encoding="utf-8"))
            posts = json.loads((Path(folder) / "posts.json").read_text(encoding="utf-8"))
        self.assertIn("keyword=react", calls[0])
        self.assertIn("location=Tehran, Iran", calls[0])
        self.assertEqual([job["url"] for job in jobs], ["https://www.linkedin.com/jobs/view/react-developer-at-acme-4011111111"])
        self.assertEqual(jobs[0]["apply_email"], "jobs@acme.ir")
        self.assertEqual(len(posts), 1)
        self.assertEqual(calls[-1][:2], ["run", "download"])


if __name__ == "__main__":
    unittest.main()
