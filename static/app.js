const form = document.querySelector("#profile-form");
const fileInput = document.querySelector("#cv-file");
const pasteInput = document.querySelector("#cv-paste");
const fileLabel = document.querySelector("#file-label");
const formError = document.querySelector("#form-error");
const statusLine = document.querySelector("#status");
const results = document.querySelector("#results");
const resultsPager = document.querySelector("#results-pager");
const postsBox = document.querySelector("#posts");
const postsPager = document.querySelector("#posts-pager");
const postSearches = document.querySelector("#post-searches");
const sourceLine = document.querySelector("#source-line");
const tracker = document.querySelector("#tracker");
const savedPager = document.querySelector("#saved-pager");
const linkedinLinks = document.querySelector("#linkedin-links");
const minScore = document.querySelector("#min-score");
const minScoreLabel = document.querySelector("#min-score-label");
const searchButton = document.querySelector("#search-button");

let currentJobs = [];
let currentPosts = [];
let currentPostSearches = [];
let savedItems = [];
let savedIds = new Set();
let jobPage = 1;
let postPage = 1;
let savedPage = 1;

const PAGE_SIZE = 5;
const PROFILE_KEY = "jobfinder.profile";
const SAVED_KEY = "jobfinder.applications";

const COUNTRIES = [
  "Iran",
  "Germany",
  "Austria",
  "United States",
  "Canada",
  "United Kingdom",
  "France",
  "Netherlands",
  "Belgium",
  "Switzerland",
  "Sweden",
  "Norway",
  "Denmark",
  "Ireland",
  "Spain",
  "Italy",
  "Portugal",
  "Poland",
  "Turkey",
  "United Arab Emirates",
];
const SEARCH_EXTRAS = ["Europe"];
const DEFAULT_COUNTRIES = ["Iran", "Germany", "Austria", "United States", "Canada"];
const COUNTRY_HINTS = {
  Iran: ["tehran", "isfahan", "esfahan", "mashhad", "shiraz", "tabriz", "karaj", "qom", "yazd", "rasht"],
  Germany: ["berlin", "munich", "hamburg", "frankfurt"],
  Austria: ["vienna", "wien", "salzburg"],
  "United States": ["usa", "u.s.", "new york", "california", "seattle", "austin", "boston"],
  Canada: ["toronto", "vancouver", "montreal", "ottawa"],
  "United Kingdom": ["uk", "london", "england", "britain"],
  France: ["paris", "lyon"],
  Netherlands: ["amsterdam", "holland"],
  Belgium: ["brussels"],
  Switzerland: ["zurich", "geneva"],
  Sweden: ["stockholm"],
  Norway: ["oslo"],
  Denmark: ["copenhagen"],
  Ireland: ["dublin"],
  Spain: ["madrid", "barcelona"],
  Italy: ["milan", "rome"],
  Portugal: ["lisbon"],
  Poland: ["warsaw"],
  Turkey: ["istanbul", "ankara", "turkiye"],
  "United Arab Emirates": ["uae", "dubai", "abu dhabi"],
};

const mobilePane = window.matchMedia("(max-width: 800px)");

document.addEventListener("DOMContentLoaded", () => {
  buildCountryControls();
  loadProfile();
  loadApplications();
  loadPosts();
  renderLinkedInLinks();
});

document.querySelector(".section-nav").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-pane]");
  if (!button) return;
  showPane(button.dataset.pane);
});

const fileDrop = document.querySelector("#file-drop");

fileInput.addEventListener("change", () => {
  const file = fileInput.files && fileInput.files[0];
  if (file) readChosenFile(file);
});

["dragenter", "dragover"].forEach((eventName) => {
  fileDrop.addEventListener(eventName, (event) => {
    event.preventDefault();
    fileDrop.classList.add("dragging");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  fileDrop.addEventListener(eventName, (event) => {
    event.preventDefault();
    fileDrop.classList.remove("dragging");
  });
});

fileDrop.addEventListener("drop", (event) => {
  const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
  if (file) readChosenFile(file);
});

function readChosenFile(file) {
  const allowed = [".pdf", ".docx", ".txt"];
  const lower = file.name.toLowerCase();
  if (!allowed.some((ext) => lower.endsWith(ext))) {
    setError("Upload a PDF, DOCX, or TXT file.");
    return;
  }
  fileLabel.textContent = file.name;
  parseFile(file);
}

document.querySelector("#read-paste").addEventListener("click", parseText);
form.addEventListener("submit", (event) => {
  event.preventDefault();
  searchJobs();
});

["titles", "location", "remote-only", "easy-apply", "all-countries"].forEach((id) => {
  const field = document.getElementById(id);
  if (!field) return;
  field.addEventListener("input", renderLinkedInLinks);
  field.addEventListener("change", () => {
    if (id === "all-countries") syncAllCountries();
    renderLinkedInLinks();
  });
});

minScore.addEventListener("input", () => {
  minScoreLabel.textContent = minScore.value;
  jobPage = 1;
  renderJobs();
});

function loadProfile() {
  const profile = readStored(PROFILE_KEY, null);
  if (profile && typeof profile === "object") applyProfile(profile);
}

async function parseFile(file) {
  const body = new FormData();
  body.append("file", file);
  await sendParse("/api/parse", { method: "POST", body });
}

async function parseText() {
  await sendParse("/api/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: pasteInput.value }),
  });
}

async function sendParse(url, options) {
  setError("");
  setStatus("Reading your CV...");
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    setStatus("");
    setError(payload.error || "Could not read that CV.");
    return;
  }
  writeStored(PROFILE_KEY, payload.profile);
  applyProfile(payload.profile);
  const count = (payload.profile.skills || []).length;
  setStatus(`Found ${count} skills and ${(payload.profile.target_titles || []).length} roles. Edit anything that looks off, then search.`);
}

function applyProfile(profile) {
  setValue("name", profile.name);
  setValue("email", profile.email);
  setValue("phone", profile.phone);
  setCountry(profile.location);
  setValue("titles", (profile.target_titles || []).join(", "));
  setValue("skills", (profile.skills || []).join(", "));
  setValue("summary", profile.summary);
  document.querySelector("#cv-text").value = profile.cv_text || "";
  if (profile.all_countries) {
    document.querySelector("#all-countries").checked = true;
  } else if (Array.isArray(profile.target_regions) && profile.target_regions.length) {
    document.querySelector("#all-countries").checked = false;
    setCheckedCountries(profile.target_regions);
  } else if (profile.name || profile.cv_text) {
    document.querySelector("#all-countries").checked = true;
  }
  syncAllCountries();
  document.querySelector("#remote-only").checked = Boolean(profile.remote_only);
  if (typeof profile.easy_apply === "boolean") {
    document.querySelector("#easy-apply").checked = profile.easy_apply;
  }
  if (profile.cv_filename) fileLabel.textContent = profile.cv_filename;
  renderLinkedInLinks();
}

async function searchJobs() {
  const titles = splitList(valueOf("titles"));
  if (!titles.length) {
    setError("Add at least one role, for example Data analyst.");
    return;
  }
  setError("");
  searchButton.disabled = true;
  setStatus("Searching job boards...");
  const profile = profilePayload();
  writeStored(PROFILE_KEY, profile);
  const response = await fetch("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  const payload = await response.json();
  searchButton.disabled = false;
  if (!response.ok) {
    setStatus("");
    setError(payload.error || "Search failed.");
    return;
  }
  currentJobs = payload.jobs || [];
  jobPage = 1;
  renderSources(payload.sources || []);
  renderJobs();
  renderPosts(payload.posts || [], payload.post_searches || []);
  if (mobilePane.matches) showPane("matches");
  const visible = visibleJobs().length;
  const postCount = (payload.posts || []).length;
  const jobNote = visible ? `${visible} roles above your match bar.` : "No roles above the match bar. Lower the bar or broaden the role titles.";
  setStatus(postCount ? `${jobNote} ${postCount} LinkedIn posts look like job offers.` : jobNote);
}

function profilePayload() {
  return {
    name: valueOf("name"),
    email: valueOf("email"),
    phone: valueOf("phone"),
    location: valueOf("location"),
    target_regions: selectedCountries(),
    all_countries: document.querySelector("#all-countries").checked,
    summary: valueOf("summary"),
    skills: splitList(valueOf("skills")),
    target_titles: splitList(valueOf("titles")),
    cv_text: document.querySelector("#cv-text").value,
    cv_filename: fileLabel.textContent,
    remote_only: document.querySelector("#remote-only").checked,
    easy_apply: document.querySelector("#easy-apply").checked,
  };
}

function renderSources(sources) {
  sourceLine.textContent = sources.map((source) => {
    if (!source.ok) return `${source.name} unavailable`;
    return `${source.name}: ${source.count}`;
  }).join(" · ");
}

function renderJobs() {
  const jobs = visibleJobs();
  results.replaceChildren();
  if (!currentJobs.length) {
    results.append(el("p", "empty", "No matching listings yet. The LinkedIn links on the left still open a search for your roles."));
    renderPager(resultsPager, 0, 1, () => {});
    return;
  }
  if (!jobs.length) {
    results.append(el("p", "empty", "Matches are below the bar. Move Minimum match to the left to see them."));
    renderPager(resultsPager, 0, 1, () => {});
    return;
  }
  const view = slicePage(jobs, jobPage);
  jobPage = view.page;
  view.items.forEach((job) => results.append(jobCard(job)));
  renderPager(resultsPager, jobs.length, jobPage, (next) => {
    jobPage = next;
    renderJobs();
    scrollTo(document.querySelector(".results-head"));
  });
}

function visibleJobs() {
  const minimum = Number(minScore.value);
  return currentJobs.filter((job) => job.score >= minimum);
}

function renderPosts(posts, searches) {
  if (!postsBox || !postSearches || !postsPager) return;
  if (Array.isArray(posts)) {
    currentPosts = posts;
    currentPostSearches = searches || [];
    postPage = 1;
  }
  postSearches.replaceChildren();
  currentPostSearches.forEach((item) => {
    if (safeUrl(item.url)) postSearches.append(linkButton(item.label, item.url, true));
  });
  postsBox.replaceChildren();
  if (!currentPosts.length) {
    postsBox.append(el("p", "empty", "No public job-offer posts yet. Use the post searches above while you are signed in to LinkedIn."));
    renderPager(postsPager, 0, 1, () => {});
    return;
  }
  const view = slicePage(currentPosts, postPage);
  postPage = view.page;
  view.items.forEach((post) => postsBox.append(postCard(post)));
  renderPager(postsPager, currentPosts.length, postPage, (next) => {
    postPage = next;
    renderPosts();
    scrollTo(postsBox.closest(".tracker"));
  });
}

function postCard(post) {
  const card = el("article", "card");
  const top = el("div", "card-top");
  const heading = el("div");
  heading.append(el("h3", null, post.title));
  const bits = [post.company, post.location, post.published ? `Posted ${post.published}` : "", "LinkedIn post"]
    .filter(Boolean)
    .join(" · ");
  heading.append(el("p", "meta", bits));
  top.append(heading);
  card.append(top);
  if (post.snippet) card.append(el("p", "snippet", post.snippet));
  if (post.reason) card.append(el("p", "reason", post.reason));
  const row = el("div", "actions");
  if (safeUrl(post.url)) row.append(linkButton("Open post", post.url, false));
  if (post.apply_email) {
    const mail = el("button", null, "Email this job");
    mail.type = "button";
    mail.addEventListener("click", () => openMail(post, mail));
    row.append(mail);
  }
  const copy = el("button", "secondary", "Copy letter");
  copy.type = "button";
  copy.addEventListener("click", () => copyText(post.cover_letter, copy));
  row.append(copy);
  card.append(row);
  if (post.cover_letter) card.append(letterBox(post.cover_letter));
  return card;
}

async function loadPosts() {
  const response = await fetch("/api/posts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(readStored(PROFILE_KEY, null) || {}),
  });
  if (!response.ok) return;
  const payload = await response.json();
  renderPosts(payload.posts || [], payload.post_searches || []);
}

function jobCard(job) {
  const card = el("article", "card");
  const top = el("div", "card-top");
  const heading = el("div");
  heading.append(el("h3", null, job.title));
  const bits = [job.company, job.location, job.remote ? "Remote" : "", job.source, job.published, job.salary]
    .filter(Boolean)
    .join(" · ");
  heading.append(el("p", "meta", bits));
  top.append(heading, scoreBadge(job));
  card.append(top);
  if (job.snippet) card.append(el("p", "snippet", job.snippet));
  card.append(el("p", "reason", job.reason));
  card.append(actionRow(job));
  card.append(letterBox(job.cover_letter));
  return card;
}

function actionRow(job) {
  const row = el("div", "actions");
  if (job.apply_email) {
    const mail = el("button", null, "Email this job");
    mail.type = "button";
    mail.addEventListener("click", () => openMail(job, mail));
    row.append(mail);
  }
  if (safeUrl(job.url)) {
    row.append(linkButton(job.apply_email ? "Open posting" : "Open application", job.url, false));
  }
  if (safeUrl(job.linkedin_search_url)) {
    row.append(linkButton("Find on LinkedIn", job.linkedin_search_url, true));
  }
  const copy = el("button", "secondary", "Copy letter");
  copy.type = "button";
  copy.addEventListener("click", () => copyText(job.cover_letter, copy));
  const save = el("button", "secondary", savedIds.has(job.id) ? "Saved" : "Save");
  save.type = "button";
  save.addEventListener("click", () => saveJob(job, save));
  row.append(copy, save);
  return row;
}

function letterBox(letter) {
  const details = document.createElement("details");
  details.append(el("summary", null, "Letter to send with your CV"));
  const area = document.createElement("textarea");
  area.readOnly = true;
  area.value = letter;
  details.append(area);
  return details;
}

function scoreBadge(job) {
  const badge = el("div", scoreClass(job.score));
  badge.append(el("strong", null, String(job.score)));
  badge.append(el("span", null, job.fit_label));
  return badge;
}

function scoreClass(score) {
  if (score >= 75) return "score high";
  if (score >= 50) return "score mid";
  return "score low";
}

function buildCountryControls() {
  const select = document.querySelector("#location");
  COUNTRIES.forEach((country) => {
    const option = document.createElement("option");
    option.value = country;
    option.textContent = country;
    select.append(option);
  });
  const grid = document.querySelector("#country-options");
  [...COUNTRIES, ...SEARCH_EXTRAS].forEach((country) => {
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = country;
    box.checked = DEFAULT_COUNTRIES.includes(country);
    box.addEventListener("change", renderLinkedInLinks);
    label.append(box, document.createTextNode(country));
    grid.append(label);
  });
  syncAllCountries();
}

function setCountry(location) {
  const select = document.querySelector("#location");
  const match = countryFromText(location);
  if (match) {
    select.value = match;
    return;
  }
  select.value = "";
}

function countryFromText(location) {
  const text = String(location || "").toLowerCase();
  if (!text) return "";
  const names = Object.keys(COUNTRY_HINTS).sort((a, b) => b.length - a.length);
  for (const country of names) {
    if (text.includes(country.toLowerCase())) return country;
    if ((COUNTRY_HINTS[country] || []).some((hint) => text.includes(hint))) return country;
  }
  return "";
}

function selectedCountries() {
  return [...document.querySelectorAll("#country-options input:checked")].map((box) => box.value);
}

function setCheckedCountries(countries) {
  const wanted = new Set(countries.map((country) => country.toLowerCase()));
  document.querySelectorAll("#country-options input").forEach((box) => {
    box.checked = wanted.has(box.value.toLowerCase());
  });
}

function syncAllCountries() {
  const all = document.querySelector("#all-countries").checked;
  const grid = document.querySelector("#country-options");
  grid.classList.toggle("is-all", all);
  grid.querySelectorAll("input").forEach((box) => {
    box.disabled = all;
  });
}

function renderLinkedInLinks() {
  const titles = splitList(valueOf("titles"));
  linkedinLinks.replaceChildren();
  if (!titles.length) {
    linkedinLinks.append(el("p", "hint", "Roles from your CV will show up here."));
    return;
  }
  const all = document.querySelector("#all-countries").checked;
  const regions = selectedCountries();
  const home = valueOf("location");
  let places = regions;
  if (all) places = home ? [home] : [];
  else if (home && !places.some((place) => place.toLowerCase() === home.toLowerCase())) places = [home, ...places];
  titles.forEach((title) => {
    if (!places.length) {
      linkedinLinks.append(linkButton(title, linkedinSearchUrl(title, ""), true));
      return;
    }
    places.forEach((place) => {
      linkedinLinks.append(linkButton(`${title} · ${place}`, linkedinSearchUrl(title, place), true));
    });
  });
}

function linkedinSearchUrl(title, place) {
  const params = new URLSearchParams();
  params.set("keywords", title);
  const location = place == null ? valueOf("location") : place;
  if (location) params.set("location", location);
  if (document.querySelector("#easy-apply").checked) params.set("f_AL", "true");
  if (document.querySelector("#remote-only").checked) params.set("f_WT", "2");
  params.set("f_TPR", "r2592000");
  return `https://www.linkedin.com/jobs/search/?${params.toString()}`;
}

function openMail(job, button) {
  const email = safeEmail(job.apply_email);
  if (!email) return;
  const subject = `Application for ${job.title} at ${job.company}`;
  const body = encodeURIComponent(job.cover_letter).replace(/%0A/g, "%0D%0A");
  const href = `mailto:${email}?subject=${encodeURIComponent(subject)}&body=${body}`;
  if (href.length > 1800) {
    copyText(job.cover_letter, button);
    window.location.href = `mailto:${email}?subject=${encodeURIComponent(subject)}`;
    setStatus("The letter was copied. Paste it into the email, attach your CV, and send.");
    return;
  }
  window.location.href = href;
  setStatus("Your email app should open. Attach your CV, then send.");
}

function saveJob(job, button) {
  const record = {
    id: String(job.id || "").slice(0, 40),
    title: String(job.title || "").slice(0, 140),
    company: String(job.company || "").slice(0, 140),
    url: safeUrl(job.url),
    source: String(job.source || "").slice(0, 40),
    score: Math.max(0, Math.min(100, Number.parseInt(job.score, 10) || 0)),
    cover_letter: String(job.cover_letter || "").slice(0, 5000),
    linkedin_search_url: safeUrl(job.linkedin_search_url),
    apply_email: safeEmail(job.apply_email),
    saved_at: new Date().toISOString(),
    status: "prepared",
  };
  if (!record.id) return;
  const items = [record, ...storedApplications().filter((item) => item.id !== record.id)].slice(0, 100);
  if (!writeStored(SAVED_KEY, items)) {
    setError("Could not save that role. This browser blocks local storage.");
    return;
  }
  button.textContent = "Saved";
  loadApplications();
}

function loadApplications() {
  savedItems = storedApplications();
  savedIds = new Set(savedItems.map((item) => item.id));
  paintSaved();
}

function storedApplications() {
  const items = readStored(SAVED_KEY, []);
  return Array.isArray(items) ? items.filter((item) => item && typeof item === "object" && item.id) : [];
}

function readStored(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (error) {
    return fallback;
  }
}

function writeStored(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch (error) {
    return false;
  }
}

function paintSaved() {
  tracker.replaceChildren();
  if (!savedItems.length) {
    tracker.append(el("p", "empty", "Roles you save show up here, with the letter to send."));
    renderPager(savedPager, 0, 1, () => {});
    return;
  }
  const view = slicePage(savedItems, savedPage);
  savedPage = view.page;
  view.items.forEach((item) => tracker.append(savedCard(item)));
  renderPager(savedPager, savedItems.length, savedPage, (next) => {
    savedPage = next;
    paintSaved();
    scrollTo(savedPager.closest(".tracker"));
  });
}

function savedCard(item) {
  const card = el("article", "saved");
  const top = el("div", "saved-top");
  const heading = el("div");
  heading.append(el("h3", null, item.title));
  heading.append(el("p", "meta", [item.company, item.source, item.score ? `Match ${item.score}` : ""].filter(Boolean).join(" · ")));
  top.append(heading);
  card.append(top);
  const row = el("div", "actions");
  if (safeUrl(item.url)) row.append(linkButton("Open application", item.url, false));
  if (safeUrl(item.linkedin_search_url)) row.append(linkButton("Find on LinkedIn", item.linkedin_search_url, true));
  if (item.apply_email) {
    const mail = el("button", null, "Email this job");
    mail.type = "button";
    mail.addEventListener("click", () => openMail(item, mail));
    row.append(mail);
  }
  const copy = el("button", "secondary", "Copy letter");
  copy.type = "button";
  copy.addEventListener("click", () => copyText(item.cover_letter, copy));
  const remove = el("button", "secondary", "Remove");
  remove.type = "button";
  remove.addEventListener("click", () => deleteSaved(item.id));
  row.append(copy, remove);
  card.append(row);
  return card;
}

function deleteSaved(id) {
  writeStored(SAVED_KEY, storedApplications().filter((item) => item.id !== id));
  loadApplications();
  renderJobs();
}

function linkButton(text, url, secondary) {
  const anchor = el("a", secondary ? "button secondary" : "button", text);
  anchor.href = url;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  return anchor;
}

async function copyText(text, button) {
  const original = button.textContent;
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  button.textContent = "Copied";
  setTimeout(() => {
    if (button.textContent === "Copied") button.textContent = original;
  }, 1400);
}

function safeEmail(value) {
  const text = String(value || "").trim();
  return /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i.test(text) ? text : "";
}

function safeUrl(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") return url;
  } catch (error) {
    return "";
  }
  return "";
}

function splitList(value) {
  return String(value || "").split(/[,;\n]/).map((item) => item.trim()).filter(Boolean);
}

function valueOf(id) {
  return document.getElementById(id).value.trim();
}

function setValue(id, value) {
  document.getElementById(id).value = value || "";
}

function slicePage(items, page) {
  const pages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  const current = Math.min(Math.max(page, 1), pages);
  const start = (current - 1) * PAGE_SIZE;
  return { items: items.slice(start, start + PAGE_SIZE), page: current, pages };
}

function renderPager(nav, total, page, onPick) {
  if (!nav) return;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (total === 0 || pages <= 1) {
    nav.hidden = true;
    nav.replaceChildren();
    return;
  }
  const current = Math.min(Math.max(page, 1), pages);
  const start = (current - 1) * PAGE_SIZE + 1;
  const end = Math.min(total, current * PAGE_SIZE);
  nav.hidden = false;
  nav.replaceChildren();
  nav.append(el("p", "pager-status", `${start}–${end} of ${total}`));
  const row = el("div", "pager-row");
  row.append(pagerButton("Previous", current === 1, () => onPick(current - 1)));
  pageWindow(pages, current).forEach((item) => {
    if (item === "…") {
      row.append(el("span", "pager-gap", "…"));
      return;
    }
    const button = pagerButton(String(item), item === current, () => onPick(item));
    if (item === current) {
      button.classList.add("is-current");
      button.setAttribute("aria-current", "page");
    }
    row.append(button);
  });
  row.append(pagerButton("Next", current === pages, () => onPick(current + 1)));
  nav.append(row);
}

function pageWindow(pages, current) {
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1);
  const items = [1];
  const left = Math.max(2, current - 1);
  const right = Math.min(pages - 1, current + 1);
  if (left > 2) items.push("…");
  for (let number = left; number <= right; number += 1) items.push(number);
  if (right < pages - 1) items.push("…");
  items.push(pages);
  return items;
}

function pagerButton(text, disabled, onClick) {
  const button = el("button", null, text);
  button.type = "button";
  button.disabled = disabled;
  if (!disabled) button.addEventListener("click", onClick);
  return button;
}

function scrollTo(node) {
  if (node) node.scrollIntoView({ behavior: "smooth", block: "start" });
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function showPane(name) {
  document.body.dataset.pane = name;
  document.querySelectorAll(".section-nav button").forEach((button) => {
    const selected = button.dataset.pane === name;
    button.classList.toggle("is-current", selected);
    if (selected) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (mobilePane.matches) {
    const root = document.documentElement;
    const previous = root.style.scrollBehavior;
    root.style.scrollBehavior = "auto";
    window.scrollTo(0, 0);
    root.style.scrollBehavior = previous;
  }
}

function setStatus(message) {
  statusLine.textContent = message;
}

function setError(message) {
  formError.hidden = !message;
  formError.textContent = message;
}
