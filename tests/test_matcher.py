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
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as folder:
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


if __name__ == "__main__":
    unittest.main()
