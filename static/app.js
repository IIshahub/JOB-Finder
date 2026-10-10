const form = document.querySelector("#profile-form");
const fileInput = document.querySelector("#cv-file");
const pasteInput = document.querySelector("#cv-paste");
const fileLabel = document.querySelector("#file-label");
const formError = document.querySelector("#form-error");
const statusLine = document.querySelector("#status");
const results = document.querySelector("#results");
const postsBox = document.querySelector("#posts");
const postSearches = document.querySelector("#post-searches");
const sourceLine = document.querySelector("#source-line");
const tracker = document.querySelector("#tracker");
const linkedinLinks = document.querySelector("#linkedin-links");
const minScore = document.querySelector("#min-score");
const minScoreLabel = document.querySelector("#min-score-label");
const searchButton = document.querySelector("#search-button");

let currentJobs = [];
let savedIds = new Set();

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

document.addEventListener("DOMContentLoaded", () => {
  buildCountryControls();
  loadProfile();
  loadApplications();
  loadPosts();
  renderLinkedInLinks();
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
  renderJobs();
});

async function loadProfile() {
  const response = await fetch("/api/profile");
  const payload = await response.json();
  if (payload.profile) applyProfile(payload.profile);
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
  const response = await fetch("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profilePayload()),
  });
  const payload = await response.json();
  searchButton.disabled = false;
  if (!response.ok) {
    setStatus("");
    setError(payload.error || "Search failed.");
    return;
  }
  currentJobs = payload.jobs || [];
  renderSources(payload.sources || []);
  renderJobs();
  renderPosts(payload.posts || [], payload.post_searches || []);
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
    return;
  }
  if (!jobs.length) {
    results.append(el("p", "empty", "Matches are below the bar. Move Minimum match to the left to see them."));
    return;
  }
  jobs.forEach((job) => results.append(jobCard(job)));
}

function visibleJobs() {
  const minimum = Number(minScore.value);
  return currentJobs.filter((job) => job.score >= minimum);
}

function renderPosts(posts, searches) {
  if (!postsBox || !postSearches) return;
  postSearches.replaceChildren();
  (searches || []).forEach((item) => {
    if (safeUrl(item.url)) postSearches.append(linkButton(item.label, item.url, true));
  });
  postsBox.replaceChildren();
  if (!posts.length) {
    postsBox.append(el("p", "empty", "No public job-offer posts yet. Use the post searches above while you are signed in to LinkedIn."));
    return;
  }
  posts.forEach((post) => postsBox.append(postCard(post)));
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
  const response = await fetch("/api/posts");
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
  const subject = `Application for ${job.title} at ${job.company}`;
  const body = encodeURIComponent(job.cover_letter).replace(/%0A/g, "%0D%0A");
  const href = `mailto:${job.apply_email}?subject=${encodeURIComponent(subject)}&body=${body}`;
  if (href.length > 1800) {
    copyText(job.cover_letter, button);
    window.location.href = `mailto:${job.apply_email}?subject=${encodeURIComponent(subject)}`;
    setStatus("The letter was copied. Paste it into the email, attach your CV, and send.");
    return;
  }
  window.location.href = href;
  setStatus("Your email app should open. Attach your CV, then send.");
}

async function saveJob(job, button) {
  const response = await fetch("/api/applications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: job.id,
      title: job.title,
      company: job.company,
      url: job.url,
      source: job.source,
      score: job.score,
      cover_letter: job.cover_letter,
      linkedin_search_url: job.linkedin_search_url,
      apply_email: job.apply_email || "",
    }),
  });
  if (!response.ok) {
    setError("Could not save that role.");
    return;
  }
  savedIds.add(job.id);
  button.textContent = "Saved";
  loadApplications();
}

async function loadApplications() {
  const response = await fetch("/api/applications");
  const payload = await response.json();
  const items = payload.applications || [];
  savedIds = new Set(items.map((item) => item.id));
  tracker.replaceChildren();
  if (!items.length) {
    tracker.append(el("p", "empty", "Roles you save show up here, with the letter to send."));
    return;
  }
  items.forEach((item) => tracker.append(savedCard(item)));
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

async function deleteSaved(id) {
  await fetch(`/api/applications/${encodeURIComponent(id)}`, { method: "DELETE" });
  savedIds.delete(id);
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

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function setStatus(message) {
  statusLine.textContent = message;
}

function setError(message) {
  formError.hidden = !message;
  formError.textContent = message;
}
