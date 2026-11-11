"""Shared Anthropic configuration, requests, and response validation."""

import json
import os
from dataclasses import dataclass
from typing import Any

import anthropic
from anthropic import Anthropic


class AnthropicConfigurationError(RuntimeError):
    """Raised when required Anthropic configuration is missing or invalid."""


class AnthropicRequestError(RuntimeError):
    """Raised with a safe, actionable message when an API request fails."""


class AnthropicResponseError(RuntimeError):
    """Raised when Claude returns an unusable response."""


@dataclass(frozen=True)
class AnthropicSettings:
    api_key: str
    model: str


def get_anthropic_settings() -> AnthropicSettings:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    model = os.getenv("ANTHROPIC_MODEL", "").strip()

    if not api_key or api_key == "sk-ant-...":
        raise AnthropicConfigurationError(
            "ANTHROPIC_API_KEY is missing. Add it to the local .env file."
        )
    if not model:
        raise AnthropicConfigurationError(
            "ANTHROPIC_MODEL is missing. Add an active Anthropic model ID to .env."
        )

    return AnthropicSettings(api_key=api_key, model=model)


def get_anthropic_client() -> Anthropic:
    settings = get_anthropic_settings()
    return Anthropic(api_key=settings.api_key)


def get_anthropic_model() -> str:
    return get_anthropic_settings().model


def _safe_request_error(exc: Exception) -> AnthropicRequestError:
    if isinstance(exc, anthropic.AuthenticationError):
        message = "Anthropic authentication failed. Check ANTHROPIC_API_KEY."
    elif isinstance(exc, (anthropic.PermissionDeniedError, anthropic.NotFoundError)):
        message = (
            "The configured Anthropic model is unavailable to this account. "
            "Check ANTHROPIC_MODEL and account access."
        )
    elif isinstance(exc, anthropic.RateLimitError):
        message = (
            "Anthropic rate or credit limit reached. Check account usage and billing, "
            "then retry."
        )
    elif isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        message = "Could not reach Anthropic. Check the network connection and retry."
    elif isinstance(exc, anthropic.BadRequestError):
        message = (
            "Anthropic rejected the request. Check ANTHROPIC_MODEL and request settings."
        )
    elif isinstance(exc, anthropic.APIStatusError):
        message = f"Anthropic returned API error {exc.status_code}. Retry later."
    else:
        message = "Unexpected Anthropic API failure. Check the server logs and retry."
    return AnthropicRequestError(message)


def create_message(client: Anthropic, **kwargs: Any):
    """Create a message using the single configured model and safe API errors."""
    try:
        return client.messages.create(model=get_anthropic_model(), **kwargs)
    except AnthropicConfigurationError:
        raise
    except Exception as exc:
        raise _safe_request_error(exc) from exc


def response_text(response: Any, operation: str) -> str:
    """Return all text blocks from a response or fail explicitly."""
    text = "\n".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()
    if not text:
        raise AnthropicResponseError(
            f"Anthropic returned no text for {operation}; manual review is required."
        )
    return text


def parse_json_response(response: Any, operation: str) -> dict[str, Any]:
    """Parse Claude's first JSON object without inventing fallback data.

    Claude occasionally surrounds otherwise valid JSON with a short explanation or a
    Markdown fence. ``raw_decode`` accepts that harmless wrapping while required-field
    checks still reject incomplete structured output.
    """
    raw = response_text(response, operation)
    if raw.startswith("```"):
        first_newline = raw.find("\n")
        closing_fence = raw.rfind("```")
        if first_newline != -1 and closing_fence > first_newline:
            raw = raw[first_newline + 1:closing_fence].strip()

    object_start = raw.find("{")
    if object_start == -1:
        raise AnthropicResponseError(
            f"Anthropic returned no JSON object for {operation}; manual review is required."
        )

    try:
        data, _ = json.JSONDecoder().raw_decode(raw[object_start:])
    except json.JSONDecodeError as exc:
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise AnthropicResponseError(
                f"Anthropic output was truncated for {operation}; increase its output limit."
            ) from exc
        raise AnthropicResponseError(
            f"Anthropic returned invalid JSON for {operation}; manual review is required."
        ) from exc

    if not isinstance(data, dict):
        raise AnthropicResponseError(
            f"Anthropic returned the wrong JSON shape for {operation}; manual review is required."
        )
    return data


def require_json_fields(
    data: dict[str, Any], required_fields: set[str], operation: str
) -> None:
    """Reject incomplete structured output instead of applying regulatory defaults."""
    missing = sorted(required_fields.difference(data))
    if missing:
        raise AnthropicResponseError(
            f"Anthropic omitted required fields for {operation}: {', '.join(missing)}. "
            "Manual review is required."
        )


def check_anthropic_connection() -> str:
    """Make a minimal request to verify credentials and model access."""
    client = get_anthropic_client()
    response = create_message(
        client,
        max_tokens=8,
        messages=[{"role": "user", "content": "Reply with OK."}],
    )
    response_text(response, "connection check")
    return get_anthropic_model()
