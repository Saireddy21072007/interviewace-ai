"""
The single seam between InterviewAce AI and any large language model.

WHY THIS FILE EXISTS
--------------------
Every other module asks for text through `LLM.complete()` / `LLM.complete_json()`.
Nothing else in the codebase imports `anthropic`, `openai` or `google.genai`.
So switching provider - or adding a self-hosted Llama later - means rewriting
exactly one file, and the resume parser, question generator and evaluator keep
working untouched.

THE OFFLINE GUARANTEE
---------------------
If no API key is configured, `LLM.available` is False and `complete_json()`
returns the caller's fallback. Every caller in this project supplies a real,
useful fallback built from rules and templates. That means the entire product
- upload a resume, get an ATS score, run a mock interview, get a report and a
roadmap - works on a laptop with no internet and no billing account. The LLM
makes the output better; it is never the difference between working and broken.
That is a demo-day requirement, not a nicety.

USAGE
-----
    from ai.llm import LLM

    llm = LLM()                      # reads .env
    if llm.available:
        text = llm.complete("You are a recruiter.", "Summarise this resume...")

    data = llm.complete_json(system, prompt, fallback=[])   # never raises
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Sensible default model per provider. Override with LLM_MODEL in .env.
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
}


class LLMError(RuntimeError):
    """Raised by complete() when a configured provider fails."""


@dataclass
class LLM:
    """A tiny, provider-agnostic chat client.

    Parameters are read from the environment when not passed explicitly, so
    application code can simply write `LLM()`.
    """

    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "auto"))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "") or "")
    api_key: str = ""
    timeout: float = 60.0

    def __post_init__(self) -> None:
        self.provider = (self.provider or "auto").strip().lower()
        if self.provider == "auto":
            self.provider = self._detect_provider()
        if self.provider != "offline" and not self.api_key:
            self.api_key = os.getenv(self._key_name(self.provider), "") or ""
        if self.provider != "offline" and not self.api_key:
            # Provider was named explicitly but its key is missing - degrade
            # rather than crash the API server on startup.
            log.warning("LLM provider %r selected but its API key is missing; "
                        "running in offline mode.", self.provider)
            self.provider = "offline"
        if not self.model:
            self.model = DEFAULT_MODELS.get(self.provider, "")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def available(self) -> bool:
        """True when a real model will answer. False means fallbacks are used."""
        return self.provider != "offline"

    def describe(self) -> dict[str, Any]:
        """Small dict for the /health and admin endpoints."""
        return {"provider": self.provider, "model": self.model, "available": self.available}

    def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 1200,
        temperature: float = 0.4,
    ) -> str:
        """Send one system+user turn, return plain text.

        Raises LLMError if the provider is unavailable or the call fails.
        Most callers should prefer `complete_json`, which never raises.
        """
        if not self.available:
            raise LLMError("No LLM provider configured (running offline).")

        try:
            if self.provider == "anthropic":
                return self._anthropic(system, user, max_tokens, temperature)
            if self.provider == "openai":
                return self._openai(system, user, max_tokens, temperature)
            if self.provider == "gemini":
                return self._gemini(system, user, max_tokens, temperature)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider SDKs raise anything
            raise LLMError(f"{self.provider} call failed: {exc}") from exc

        raise LLMError(f"Unknown provider {self.provider!r}")

    def complete_json(
        self,
        system: str,
        user: str,
        fallback: Any,
        *,
        max_tokens: int = 1600,
        temperature: float = 0.3,
    ) -> Any:
        """Ask for JSON and parse it. Returns `fallback` on ANY problem.

        This is the method the rest of the codebase uses, because an interview
        must never fail because a model was rate-limited.
        """
        system = system.rstrip() + (
            "\n\nRespond with valid JSON only. No markdown fences, no prose "
            "before or after the JSON."
        )
        try:
            raw = self.complete(system, user, max_tokens=max_tokens, temperature=temperature)
        except LLMError as exc:
            log.info("LLM unavailable, using fallback: %s", exc)
            return fallback
        except Exception as exc:  # noqa: BLE001
            # complete() normally wraps provider errors in LLMError, but this
            # method's contract with the rest of the codebase is that it NEVER
            # raises. A rate limit or a bad gateway must not end an interview,
            # so anything that gets this far still degrades to the fallback.
            log.warning("Unexpected LLM error, using fallback: %s", exc)
            return fallback

        parsed = extract_json(raw)
        if parsed is None:
            log.warning("LLM returned unparseable JSON, using fallback. Head: %.160s", raw)
            return fallback
        return parsed

    # ------------------------------------------------------------------ #
    # Provider implementations - the only vendor-specific code in the repo
    # ------------------------------------------------------------------ #

    def _anthropic(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        import anthropic  # imported lazily so the package stays optional

        client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout)
        msg = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in msg.content if block.type == "text").strip()

    def _openai(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, timeout=self.timeout)
        resp = client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

    def _gemini(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        resp = client.models.generate_content(
            model=self.model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        return (resp.text or "").strip()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _key_name(provider: str) -> str:
        return {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }.get(provider, "")

    @staticmethod
    def _detect_provider() -> str:
        """Pick the first provider whose key is actually set."""
        for provider in ("anthropic", "openai", "gemini"):
            if os.getenv(LLM._key_name(provider), "").strip():
                return provider
        return "offline"


# ---------------------------------------------------------------------- #
# JSON extraction - models love to wrap JSON in prose or ``` fences
# ---------------------------------------------------------------------- #

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> Any | None:
    """Best-effort parse of a JSON object/array out of model output.

    Tries, in order: the whole string, any ``` fenced block, then the widest
    {...} or [...] slice. Returns None if nothing parses.
    """
    if not text:
        return None

    candidates: list[str] = [text.strip()]

    fenced = _FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1).strip())

    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


# A module-level singleton is convenient for the API layer, which would
# otherwise re-read the environment on every request.
_default: LLM | None = None


def get_llm() -> LLM:
    """Return the process-wide LLM instance (created on first use)."""
    global _default
    if _default is None:
        _default = LLM()
        log.info("LLM ready: %s", _default.describe())
    return _default


def reset_llm() -> None:
    """Drop the cached instance - used by tests and by /admin config reloads."""
    global _default
    _default = None
