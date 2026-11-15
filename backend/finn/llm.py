"""Model routing, caching and cost logging.

Every call names a *task*; the task picks a tier (small / mid / strong) and an ordered list of
providers, so a rate limit on one falls through to the next. Outputs are JSON and cached by
sha256(task + prompt version + model + content), so nothing is processed twice.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from typing import Any

import httpx

from . import config
from .db import session_scope
from .models import LlmCache, LlmLog

log = logging.getLogger("finn.llm")

PROMPT_VERSION = "v1"

# task -> ordered providers (first that has a key and succeeds wins)
ROUTES: dict[str, list[str]] = {
    "classify": ["groq_small", "gemini_small"],
    "summary": ["gemini_small", "groq_small"],
    "bio": ["gemini_small", "groq_small"],
    "results": ["gemini_mid", "gemini_small"],  # reads PDFs directly
    "claims": ["gemini_mid", "gemini_small"],
    "exposures": ["gemini_mid", "gemini_small"],
    "snapshot": ["gemini_mid", "gemini_small"],
    "verdict": ["gemini_strong", "gemini_mid"],
    "bullbear": ["gemini_strong", "gemini_mid"],
    "answer": ["gemini_mid", "gemini_strong"],
    "intent": ["groq_small", "gemini_small"],
}


class LLMUnavailable(RuntimeError):
    pass


_DEAD: set[str] = set()


def _has_key(provider: str) -> bool:
    if provider in _DEAD:
        return False
    return bool(config.GROQ_API_KEY if provider.startswith("groq") else config.GEMINI_API_KEY)


def available(task: str) -> bool:
    return any(_has_key(p) for p in ROUTES[task])


def _cache_key(task: str, model: str, prompt: str, pdf: bytes | None) -> str:
    h = hashlib.sha256()
    for part in (task, PROMPT_VERSION, model, prompt):
        h.update(part.encode())
        h.update(b"\x00")
    if pdf:
        h.update(hashlib.sha256(pdf).digest())
    return h.hexdigest()


def parse_json(text: str) -> Any:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
        if start < 0:
            raise
        end = max(text.rfind("}"), text.rfind("]"))
        return json.loads(text[start : end + 1])


def _gemini(model: str, prompt: str, pdf: bytes | None, system: str) -> tuple[Any, int, int]:
    parts: list[dict] = [{"text": prompt}]
    if pdf:
        parts.insert(0, {"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(pdf).decode()}})
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = httpx.post(url, headers={"x-goog-api-key": config.GEMINI_API_KEY}, json=body, timeout=180)
    if r.status_code in (404, 429, 401, 403):
        raise LLMUnavailable(f"gemini {model}: {r.status_code} {r.text[:200]}")
    r.raise_for_status()
    data = r.json()
    text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    usage = data.get("usageMetadata", {})
    return parse_json(text), usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0)


def _groq(model: str, prompt: str, system: str) -> tuple[Any, int, int]:
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        json={"model": model, "messages": messages, "temperature": 0.1, "response_format": {"type": "json_object"}},
        timeout=60,
    )
    if r.status_code in (404, 429, 401, 403):
        raise LLMUnavailable(f"groq {model}: {r.status_code} {r.text[:200]}")
    r.raise_for_status()
    data = r.json()
    usage = data.get("usage", {})
    return parse_json(data["choices"][0]["message"]["content"]), usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


def call(task: str, prompt: str, *, pdf: bytes | None = None, system: str = "", use_cache: bool = True) -> Any:
    """Run `task` on the first available provider. Returns parsed JSON. Raises LLMUnavailable."""
    errors = []
    for provider in ROUTES[task]:
        if not _has_key(provider):
            continue
        if pdf and provider.startswith("groq"):
            continue
        model = config.MODELS[provider]
        key = _cache_key(task, model, system + prompt, pdf)
        if use_cache:
            with session_scope() as s:
                hit = s.get(LlmCache, key)
                if hit:
                    s.add(LlmLog(task=task, model=model, cached=True))
                    return hit.output
        for attempt in range(2):
            try:
                t0 = time.time()
                if provider.startswith("groq"):
                    out, tin, tout = _groq(model, prompt, system)
                else:
                    out, tin, tout = _gemini(model, prompt, pdf, system)
                log.info("llm %s %s %.1fs in=%s out=%s", task, model, time.time() - t0, tin, tout)
                with session_scope() as s:
                    s.merge(LlmCache(key=key, task=task, model=model, output=out))
                    s.add(LlmLog(task=task, model=model, tokens_in=tin, tokens_out=tout))
                return out
            except LLMUnavailable as e:
                errors.append(f"{model}: {e}")
                if " 404 " in str(e) or " 401 " in str(e) or " 403 " in str(e):
                    _DEAD.add(provider)
                    log.error("disabling %s for this run: %s", provider, e)
                break  # rate limited / unavailable: try next provider
            except Exception as e:  # network / parse error: retry once, then next provider
                errors.append(f"{model}: {e}")
                if attempt == 0:
                    time.sleep(1.5)
        with session_scope() as s:
            s.add(LlmLog(task=task, model=model, ok=False))
    raise LLMUnavailable(f"no provider succeeded for {task}: {errors or 'no API key set'}")


def transcribe(audio: bytes, filename: str = "voice.m4a") -> str:
    """Speech to text with Whisper on Groq."""
    if not config.GROQ_API_KEY:
        raise LLMUnavailable("GROQ_API_KEY not set")
    r = httpx.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        files={"file": (filename, audio)},
        data={"model": config.MODELS["groq_whisper"], "language": "en", "response_format": "json"},
        timeout=60,
    )
    r.raise_for_status()
    with session_scope() as s:
        s.add(LlmLog(task="stt", model=config.MODELS["groq_whisper"]))
    return r.json().get("text", "").strip()
