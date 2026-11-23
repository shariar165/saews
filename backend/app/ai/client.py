"""The single place that talks to the Anthropic API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel

from ..config import get_settings

log = logging.getLogger("saews.ai")

T = TypeVar("T", bound=BaseModel)

# On a policy decline the API re-runs the same request on a suitable fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AIUnavailable(Exception):
    """AI is disabled, not configured, refused, or failed. Callers fall back to the non-AI behaviour."""


@dataclass
class AIResult:
    data: BaseModel
    model: str
    input_tokens: int | None
    output_tokens: int | None


def is_enabled() -> bool:
    s = get_settings()
    return bool(s.ai_enabled and s.anthropic_api_key and s.anthropic_api_key.get_secret_value().strip())


@lru_cache
def _client():
    import anthropic  # imported lazily so the app starts even where the package is missing

    s = get_settings()
    return anthropic.Anthropic(api_key=s.anthropic_api_key.get_secret_value(), timeout=s.ai_timeout_seconds,
                               max_retries=2)


def get_client():
    """Indirection point; tests replace this with a fake client."""
    return _client()


def generate(schema: type[T], *, system: str, prompt: str, max_tokens: int = 4000) -> AIResult:
    """Ask Claude for a response that validates against ``schema``. Raises AIUnavailable on any failure."""
    if not is_enabled():
        raise AIUnavailable("The AI assistant is not enabled on this server.")
    import anthropic

    s = get_settings()
    try:
        response = get_client().beta.messages.parse(
            model=s.ai_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            output_config={"effort": s.ai_effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.APIConnectionError as e:
        log.warning("AI connection error: %s", e)
        raise AIUnavailable("The AI service could not be reached. Please try again later.") from e
    except anthropic.RateLimitError as e:
        log.warning("AI rate limited: %s", e)
        raise AIUnavailable("The AI service is busy. Please try again in a minute.") from e
    except anthropic.APIStatusError as e:
        log.warning("AI API error %s (request %s): %s", e.status_code, getattr(e, "request_id", None), e.message)
        raise AIUnavailable("The AI service returned an error. Please try again later.") from e
    except (anthropic.AnthropicError, ValueError) as e:  # ValueError covers a structured output that fails validation
        log.warning("AI error: %s", e)
        raise AIUnavailable("The AI service returned an unusable answer. Please try again.") from e

    if response.stop_reason == "refusal":
        raise AIUnavailable("The AI assistant declined this request. Please write this text manually.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise AIUnavailable("The AI answer was incomplete. Please try again.")
    usage = response.usage
    return AIResult(data=response.parsed_output, model=response.model,
                    input_tokens=getattr(usage, "input_tokens", None), output_tokens=getattr(usage, "output_tokens", None))
