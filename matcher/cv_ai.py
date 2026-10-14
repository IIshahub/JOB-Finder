"""Read a CV with an AI model when an API key is set.

Tries every configured provider and model in order. When one is busy, rate
limited, or out of free tokens, the next one is used. Supports OpenRouter free
models, Google Gemini, Groq, and any OpenAI-compatible endpoint such as Ollama.
Without a key nothing is sent anywhere.
"""

from __future__ import annotations

import json
import logging
import os
import re

import requests

log = logging.getLogger(__name__)

MAX_CHARS = 24000
TIMEOUT = 45
TEXT_FIELDS = ("name", "email", "phone", "location", "linkedin", "summary")

# Free OpenRouter models tried in this order when CV_AI_MODEL is empty.
OPENROUTER_FREE_MODELS = (
    "google/gemma-4-31b-it:free,"
    "nvidia/nemotron-3-super-120b-a12b:free,"
    "google/gemma-4-26b-a4b-it:free,"
    "openrouter/free"
)
GEMINI_MODELS = "gemini-2.5-flash,gemini-2.0-flash,gemini-2.5-flash-lite"
GROQ_MODELS = "openai/gpt-oss-20b,qwen/qwen3.8-27b,openai/gpt-oss-120b"
OLLAMA_DEFAULT = "http://127.0.0.1:11434/v1"

PROMPT = """Read the CV below and return one JSON object with exactly these keys:
name, email, phone, location, linkedin, summary, skills, target_titles.

- name: the person's full name.
- location: the city and country where the person lives, like "Tehran, Iran". Empty if the CV does not say.
- linkedin: the full LinkedIn profile URL, or "".
- summary: the CV's own summary or profile text, at most 600 characters. If there is none, write one or two plain sentences based on the CV.
- skills: up to 40 concrete skills, tools, technologies, and methods the CV lists or shows in use. Short names only, like "React", "SQL", or "Financial Analysis". Leave out anything marked as beginner, and leave out spoken languages.
- target_titles: up to 6 job titles this person fits, most relevant first: the headline under the name, then titles from their work experience. Titles only, without company names, dates, or locations. Keep Persian titles in Persian.

Use "" or [] for anything the CV does not contain. Never invent contact details.
The CV text may be out of order if it came from a PDF with columns.

CV:
"""


class AiReadError(Exception):
    """The AI service could not be used for this CV."""


def ai_configured() -> bool:
    return bool(providers())


def settings() -> dict | None:
    """Return the first configured provider, for older callers and tests."""
    found = providers()
    return found[0] if found else None


def providers() -> list[dict]:
    """Return every configured AI backend, each with one or more models.

    Order: OpenRouter / OpenAI-compatible, then Gemini, then Groq, then Ollama.
    Keys that are set are all used; missing keys are skipped.
    """
    found: list[dict] = []
    model = os.environ.get("CV_AI_MODEL", "").strip()

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    base = os.environ.get("OPENAI_BASE_URL", "").strip()
    key = openrouter_key or openai_key
    if key:
        use_openrouter = bool(openrouter_key) or "openrouter.ai" in base or key.startswith("sk-or-")
        if use_openrouter:
            models = openrouter_models(model)
            if models:
                found.append(
                    {
                        "name": "OpenRouter",
                        "provider": "openai",
                        "key": key,
                        "base": (base or "https://openrouter.ai/api/v1").rstrip("/"),
                        "model": models,
                    }
                )
        elif not looks_like_ollama(base):
            found.append(
                {
                    "name": "OpenAI",
                    "provider": "openai",
                    "key": key,
                    "base": (base or "https://api.openai.com/v1").rstrip("/"),
                    "model": model or "gpt-4o-mini",
                }
            )

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        gemini_models = os.environ.get("CV_AI_GEMINI_MODELS", "").strip() or (
            model if model and "gemini" in model.lower() else GEMINI_MODELS
        )
        if model and "gemini" not in model.lower() and not os.environ.get("CV_AI_GEMINI_MODELS"):
            gemini_models = GEMINI_MODELS
        found.append(
            {
                "name": "Gemini",
                "provider": "gemini",
                "key": gemini_key,
                "base": "https://generativelanguage.googleapis.com/v1beta",
                "model": gemini_models,
            }
        )

    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        found.append(
            {
                "name": "Groq",
                "provider": "openai",
                "key": groq_key,
                "base": "https://api.groq.com/openai/v1",
                "model": os.environ.get("CV_AI_GROQ_MODELS", "").strip() or GROQ_MODELS,
            }
        )

    ollama_model = os.environ.get("OLLAMA_MODEL", "").strip()
    if ollama_model or looks_like_ollama(base) or looks_like_ollama(os.environ.get("OLLAMA_BASE_URL", "")):
        ollama_base = (
            os.environ.get("OLLAMA_BASE_URL", "").strip()
            or (base if looks_like_ollama(base) else "")
            or OLLAMA_DEFAULT
        ).rstrip("/")
        if not ollama_base.endswith("/v1"):
            ollama_base = ollama_base.rstrip("/") + "/v1"
        found.append(
            {
                "name": "Ollama",
                "provider": "openai",
                "key": os.environ.get("OLLAMA_API_KEY", "").strip() or "ollama",
                "base": ollama_base,
                "model": ollama_model or model or "qwen3:4b-instruct",
            }
        )

    return found


def looks_like_ollama(url: str) -> bool:
    text = (url or "").lower()
    return "11434" in text or "ollama" in text


def openrouter_models(requested: str) -> str:
    """Keep only free OpenRouter models unless CV_AI_ALLOW_PAID is set."""
    models = [name.strip() for name in (requested or OPENROUTER_FREE_MODELS).split(",") if name.strip()]
    if os.environ.get("CV_AI_ALLOW_PAID", "").strip().lower() in {"1", "true", "yes"}:
        return ",".join(models)
    free = []
    for name in models:
        if name.endswith(":free") or name == "openrouter/free":
            free.append(name)
    if len(free) < len(models):
        log.warning("Skipping paid OpenRouter models: %s", ", ".join(set(models) - set(free)))
    return ",".join(free)


def ai_parse(text: str) -> tuple[dict, str]:
    """Return the fields the model found and the model that answered.

    Tries every provider and every model in its list. Raises AiReadError only
    when all of them fail.
    """
    targets = providers()
    if not targets:
        raise AiReadError("No AI key is set.")
    prompt = PROMPT + text[:MAX_CHARS]
    error = AiReadError("The AI reader could not be reached.")
    for config in targets:
        models = [name.strip() for name in config["model"].split(",") if name.strip()]
        for model in models:
            label = f"{config['name']}/{model}"
            try:
                profile = ask_model({**config, "model": model}, prompt)
                log.info("CV read with %s", label)
                return profile, label
            except AiReadError as exc:
                log.warning("Skipping %s: %s", label, exc)
                error = exc
    raise error


def ask_model(config: dict, prompt: str) -> dict:
    try:
        if config["provider"] == "openai":
            reply = ask_openai(config, prompt)
        else:
            reply = ask_gemini(config, prompt)
    except requests.RequestException as exc:
        log.warning("AI CV reader could not reach %s: %s", config["model"], exc)
        raise AiReadError("The AI reader could not be reached.") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        log.warning("AI CV reader got an unexpected reply from %s: %s", config["model"], exc)
        raise AiReadError("The AI reader sent an unexpected reply.") from exc
    return clean_reply(load_json(reply))


def ask_openai(config: dict, prompt: str) -> str:
    body = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": "You read CVs and reply with one JSON object only."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {config['key']}"}
    if "openrouter.ai" in config["base"]:
        headers["HTTP-Referer"] = "http://127.0.0.1:5050"
        headers["X-Title"] = "CV Job Matcher"
    url = f"{config['base']}/chat/completions"
    response = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
    # Some free and local models do not support JSON mode; the prompt asks for JSON anyway.
    if response.status_code in {400, 404, 422}:
        body.pop("response_format", None)
        response = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
    if response.status_code in {402, 403, 429, 503}:
        raise AiReadError(f"Model unavailable ({response.status_code}).")
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def ask_gemini(config: dict, prompt: str) -> str:
    response = requests.post(
        f"{config['base']}/models/{config['model']}:generateContent",
        headers={"x-goog-api-key": config["key"]},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        timeout=TIMEOUT,
    )
    if response.status_code in {402, 403, 429, 503}:
        raise AiReadError(f"Model unavailable ({response.status_code}).")
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def load_json(reply: str) -> dict:
    reply = (reply or "").strip()
    fenced = re.search(r"\{.*\}", reply, re.S)
    if fenced:
        reply = fenced.group(0)
    try:
        data = json.loads(reply)
    except json.JSONDecodeError as exc:
        raise AiReadError("The AI reader sent an unexpected reply.") from exc
    if not isinstance(data, dict):
        raise AiReadError("The AI reader sent an unexpected reply.")
    return data


def clean_reply(data: dict) -> dict:
    from matcher.cv_parser import EMAIL_RE, LINKEDIN_RE

    profile = {field: text_value(data.get(field)) for field in TEXT_FIELDS}
    if profile["email"] and not EMAIL_RE.fullmatch(profile["email"]):
        profile["email"] = ""
    linkedin = profile["linkedin"]
    if linkedin and not linkedin.lower().startswith("http"):
        linkedin = "https://" + linkedin.lstrip("/")
    profile["linkedin"] = linkedin if LINKEDIN_RE.match(linkedin) else ""
    digits = re.sub(r"\D", "", profile["phone"])
    if not 7 <= len(digits) <= 15:
        profile["phone"] = ""
    profile["summary"] = profile["summary"][:600]
    profile["skills"] = text_list(data.get("skills"), limit=40, item_limit=60)
    profile["target_titles"] = text_list(data.get("target_titles"), limit=6, item_limit=80)
    return profile


def text_value(value) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:600]


def text_list(values, limit: int, item_limit: int) -> list[str]:
    if not isinstance(values, list):
        return []
    found = []
    seen = set()
    for value in values:
        item = text_value(value)[:item_limit]
        if not item or item.lower() in seen:
            continue
        seen.add(item.lower())
        found.append(item)
        if len(found) >= limit:
            break
    return found
