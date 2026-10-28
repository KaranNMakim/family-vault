"""LLM access, only through LLMClient.

The LLM is used for exactly two things: rephrasing onboarding questions and rewording checklist
steps in plain language. It never sees family data: callers pass a StructuralContext containing
only whitelisted keys whose values are enums, counts or our own template text with
``{placeholders}``. Real values (names, institutions, dates) are substituted AFTER the LLM call.

LLM_MODE=mock (default) is deterministic and offline. LLM_MODE=live calls the Anthropic API and
falls back to the template text on any error, refusal, or a reply that drops a placeholder.
"""

from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import BaseModel, field_validator

from app.config import get_settings
from app.logs import get_logger

log = get_logger("llm")

ALLOWED_KEYS = {
    "section", "slot", "asset_type", "institution_kind", "scenario", "action", "doc_types",
    "actor_role", "blocked", "step_index", "people_count", "assets_count", "template",
}
_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")
_SAFE_STR = re.compile(r"^[A-Za-z0-9 ,.;:'’()/?!\-_{}&]*$")
_DIGIT_RUN = re.compile(r"\d{3,}")


class LLMGuardError(ValueError):
    pass


class StructuralContext(BaseModel):
    task: Literal["onboarding_question", "checklist_step"]
    fields: dict[str, str | int | bool | list[str]]

    @field_validator("fields")
    @classmethod
    def _guard(cls, v: dict) -> dict:
        for key, value in v.items():
            if key not in ALLOWED_KEYS:
                raise LLMGuardError(f"key {key!r} may not be sent to the LLM")
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, bool):
                    continue
                if isinstance(item, int):
                    if not 0 <= item <= 999:
                        raise LLMGuardError(f"{key}: numbers sent to the LLM must be small counts")
                    continue
                if len(item) > 400 or not _SAFE_STR.match(item) or _DIGIT_RUN.search(item):
                    raise LLMGuardError(f"{key}: only structural text (no digits or data) may be sent")
        return v

    @property
    def template(self) -> str:
        return str(self.fields.get("template", ""))


class LLMClient(Protocol):
    mode: str

    def rephrase(self, ctx: StructuralContext) -> str: ...


class MockLLM:
    """Deterministic: returns the template unchanged."""

    mode = "mock"

    def __init__(self) -> None:
        self.calls: list[StructuralContext] = []

    def rephrase(self, ctx: StructuralContext) -> str:
        self.calls.append(ctx)
        return ctx.template


SYSTEM_PROMPT = (
    "You rewrite one short sentence for an Indian household estate-planning app used by older family "
    "members. Make it warm, plain and clear (Indian English, no jargon, at most 30 words). Keep every "
    "{placeholder} exactly as written. Output only the rewritten sentence."
)


class AnthropicLLM:
    mode = "live"

    def __init__(self, model: str):
        import anthropic

        self._client = anthropic.Anthropic(max_retries=1, timeout=20.0)
        self._model = model
        self._cache: dict[str, str] = {}

    def rephrase(self, ctx: StructuralContext) -> str:
        key = ctx.model_dump_json()
        if key in self._cache:
            return self._cache[key]
        template = ctx.template
        prompt = f"Task: {ctx.task}\nContext: {ctx.fields}\nSentence: {template}"
        try:
            resp = self._client.beta.messages.create(
                model=self._model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=[{"role": "user", "content": prompt}],
            )
            if resp.stop_reason == "refusal":
                return template
            text = next((b.text for b in resp.content if b.type == "text"), "").strip()
        except Exception as e:  # offline, auth, rate limit... the demo must keep working
            log.warning("llm call failed, using template", extra={"error": type(e).__name__})
            return template
        if not text or set(_PLACEHOLDER.findall(text)) != set(_PLACEHOLDER.findall(template)):
            return template
        self._cache[key] = text
        return text


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = AnthropicLLM(s.llm_model) if s.llm_mode == "live" else MockLLM()
    return _client


def fill(text: str, **values: str) -> str:
    """Substitute real values into placeholders after the LLM step."""
    for k, v in values.items():
        text = text.replace("{" + k + "}", v)
    return text
