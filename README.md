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

The `data` folder holds the saved CV and the ready-to-send list on this computer. It is not part of the published project. Delete that folder to clear them.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_matcher
```
