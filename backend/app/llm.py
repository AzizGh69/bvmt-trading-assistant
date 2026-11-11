"""One OpenAI-compatible chat client for every LLM feature.

``LLM_BASE_URL``, ``LLM_API_KEY`` and ``LLM_MODEL`` select the provider:
OpenAI, Groq, OpenRouter or anything else that serves ``/chat/completions``.
With no key, :func:`chat` raises :class:`LLMNotConfigured` and every caller has
a fallback. Call it as ``llm.chat(...)`` so tests can replace it.
"""
from __future__ import annotations

import json
import logging

import httpx

from .config import Settings, get_settings

log = logging.getLogger("bvmt.llm")


class LLMNotConfigured(RuntimeError):
    pass


class LLMError(RuntimeError):
    pass


def chat(
    messages: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int = 700,
    json_mode: bool = False,
    settings: Settings | None = None,
) -> str:
    """Send a chat completion request and return the reply text."""
    settings = settings or get_settings()
    if not settings.llm_configured:
        raise LLMNotConfigured("LLM_API_KEY is not set")
    body: dict = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        response = httpx.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"] or ""
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        # The message names the status or the failure, never the key.
        log.warning("LLM call failed: %s", type(exc).__name__)
        raise LLMError(f"the language model did not answer ({type(exc).__name__})") from exc


def chat_json(messages: list[dict], **kwargs) -> dict:
    """A chat completion that must answer one JSON object."""
    text = chat(messages, json_mode=True, **kwargs).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError("the language model did not answer JSON") from exc
    if not isinstance(value, dict):
        raise LLMError("the language model did not answer a JSON object")
    return value
