# JOB Finder

A local matcher that reads your CV, finds open roles that fit it, and prepares a short letter for each one. You review the matches and send the applications yourself.

Your CV stays on this computer. The app does not log in to LinkedIn, attach your file, or send email.

## What you get

- A profile from a PDF, DOCX, or pasted CV: name, contact details, roles, and skills.
- Ranked jobs from public boards. The country where you live is listed first.
- A letter you can copy into an application or email.
- LinkedIn search links for each role and country. You sign in, attach your CV, and apply.
- Public LinkedIn posts that read as job offers, plus a signed-in search link for more of the feed.
- A local list of roles you marked ready to send.

## Job boards

Iran listings come from [Jobvision](https://jobvision.ir/), [Jobinja](https://jobinja.ir/), [e-Estekhdam](https://www.e-estekhdam.com/), [Quera](https://quera.org/), [IranTalent](https://www.irantalent.com/), and [Kardix](https://kardix.com/).

Roles outside Iran come from [Remotive](https://remotive.com/), [Arbeitnow](https://www.arbeitnow.com/), [Remote OK](https://remoteok.com/), and [Jobicy](https://jobicy.com/).

## New LinkedIn jobs and posts

New public LinkedIn job listings and hiring posts are found with [Tavily](https://tavily.com/), a web search API. Nothing here talks to LinkedIn itself. Tavily's free plan gives 1,000 searches a month and does not ask for a card.

Tavily refuses connections from Iranian servers, so the search runs in GitHub Actions instead, and the app needs no key:

1. Every twelve hours, `.github/workflows/linkedin-posts.yml` runs `scripts/update_post_feed.py`. For each of six roles it searches posts and `search_web_jobs` listings from the past month, and commits the results to `feed/linkedin_posts.json` and `feed/linkedin_jobs.json`.
2. The app downloads both files from GitHub at most once an hour and keeps them in `data/`. LinkedIn jobs are ranked with the other boards when you click **Find matching jobs**, and posts are shown in their own list.

To set it up, add your Tavily key as a repository secret named `TAVILY_API_KEY` under **Settings → Secrets and variables → Actions**. To run it right away, open **Actions → LinkedIn post feed → Run workflow**.

To change the roles, add a repository variable named `FEED_ROLES` with comma-separated titles, or edit `DEFAULT_ROLES` in the script. Each role costs two searches per run, one for posts and one for jobs; six roles at two runs a day is about 744 searches a month, under the free plan.

On a server that can reach Tavily directly, set `POSTS_FEED_URL` and `JOBS_FEED_URL` to empty values and `TAVILY_API_KEY` to your key. The app then searches the roles each visitor types.

## Search LinkedIn by keyword

`scripts/search_linkedin.py` finds LinkedIn job listings and hiring posts that contain every word of a keyword:

```powershell
python -m scripts.search_linkedin react developer --location "Tehran, Iran"
python -m scripts.search_linkedin "data analyst" --since week --json results.json
python -m scripts.search_linkedin فرانت --offline
```

- **Jobs** are public `linkedin.com/jobs/view` pages, and **posts** are public `linkedin.com/posts` pages. Both are found with Tavily, so this needs `TAVILY_API_KEY` or `--api-key`.
- Saved posts in `feed/` and `data/` are always searched, so `--offline` works without a key or a connection.
- `--since` is `day`, `week`, `month` (the default), or `year`. Each run without `--offline` uses two Tavily searches.
- The output ends with signed-in LinkedIn search links for jobs and posts with the same keyword, for anything the web search missed.

Tavily answers 403 Forbidden from Iranian networks. In that case only saved posts are shown, and the error appears under **Sources**.

From Iran, add `--remote` instead. The search then runs in GitHub Actions (`.github/workflows/linkedin-search.yml`) with the repository's `TAVILY_API_KEY` secret, and the results are downloaded in about a minute:

```powershell
python -m scripts.search_linkedin react developer --location "Tehran, Iran" --remote
```

This needs the [GitHub CLI](https://cli.github.com/) signed in with `gh auth login`. The jobs and posts it finds are also saved to `data/`, so **Find matching jobs** in the app shows them right away.

## Run it

On Windows, double-click `run.bat`. It creates a virtual environment, installs the packages, and opens the app at [http://127.0.0.1:5050](http://127.0.0.1:5050).

From a terminal:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

Then open [http://127.0.0.1:5050](http://127.0.0.1:5050).

## Use it

1. Drop in a PDF, DOCX, or TXT CV, or paste the text. Scanned pages need the pasted text.
2. Check the name, roles, and skills. Fix anything the parser missed.
3. Choose the country where you live. Jobs there stay at the top.
4. Check more countries, or choose **All countries**.
5. Click **Find matching jobs**.
6. Open a match, copy the letter, attach your CV, and send it yourself.

**Remote roles only** hides on-site jobs. **LinkedIn Easy Apply** is only a filter on the LinkedIn links. The match bar hides weaker results; move it left to see more.

## What stays private

Your CV and the ready-to-send list are kept in your own browser, not on the server. Another device or browser starts empty. To clear them, clear this site's data in your browser.

The server reads an uploaded CV to pull out your details and sends them back without saving them. The `data` folder only holds public LinkedIn posts found by web search.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_matcher
```
