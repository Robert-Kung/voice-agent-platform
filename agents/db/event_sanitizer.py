"""Sanitize structured event payloads before persistence/API output."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# v2 adds llm_text run event types (llm_response / token_usage / edge_selected)
# and pattern-based sanitization for natural-language LLM output.
SCHEMA_VERSION = 2
REDACTED = "<redacted>"

_SECRET_KEY_PARTS = (
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "secret",
    "token",
    "password",
    "passwd",
    "credential",
    "bearer",
    "cookie",
    "set-cookie",
)

_ENV_SECRET_PREFIXES = (
    "AWS_",
    "AZURE_",
    "GOOGLE_",
    "GCP_",
    "LIVEKIT_",
    "DEEPGRAM_",
    "OPENAI_",
    "ANTHROPIC_",
    "GEMINI_",
)

_ENV_SECRET_NAMES = {
    "DATABASE_URL",
    "ADMIN_API_TOKEN",
    "ADMIN_PASSWORD",
}

# Token *count* fields (LLM usage metrics) are not credentials.
_SAFE_KEYS = {
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cached_tokens",
    "token_usage",
}


def sanitize_event_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a sanitized copy of an event payload with a schema version.

    Redaction is intentionally conservative. Key names that look like secrets are
    redacted anywhere in nested objects, including headers, query params, and
    tool config snapshots. Environment variable names with known secret prefixes
    are also redacted.
    """
    sanitized = _sanitize_value(payload or {}, path=())
    if not isinstance(sanitized, dict):
        sanitized = {"value": sanitized}
    sanitized.setdefault("schema_version", SCHEMA_VERSION)
    return sanitized


def _sanitize_value(value: Any, *, path: tuple[str, ...]) -> Any:
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, child in value.items():
            key_str = str(key)
            child_path = (*path, key_str)
            if _is_sensitive_key(key_str):
                clean[key_str] = REDACTED
            elif _looks_like_env_secret_reference(key_str, child):
                clean[key_str] = REDACTED
            else:
                clean[key_str] = _sanitize_value(child, path=child_path)
        return clean

    if isinstance(value, str):
        if _is_sensitive_path(path) and value:
            return REDACTED
        return _sanitize_url_query(value)

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize_value(item, path=path) for item in value]

    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    if normalized in _SAFE_KEYS:
        return False
    return any(part in normalized for part in _SECRET_KEY_PARTS)


def _is_sensitive_path(path: tuple[str, ...]) -> bool:
    return any(_is_sensitive_key(part) for part in path)


def _looks_like_env_secret_reference(key: str, value: Any) -> bool:
    candidates = [key]
    if isinstance(value, str):
        candidates.append(value)
    for candidate in candidates:
        env_name = candidate.strip().upper()
        if env_name in _ENV_SECRET_NAMES:
            return True
        if any(env_name.startswith(prefix) for prefix in _ENV_SECRET_PREFIXES):
            return True
    return False


def _sanitize_url_query(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.scheme or not parsed.netloc or not parsed.query:
        return value

    changed = False
    query_items: list[tuple[str, str]] = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        if _is_sensitive_key(key) or _looks_like_env_secret_reference(key, item_value):
            query_items.append((key, REDACTED))
            changed = True
        else:
            query_items.append((key, item_value))

    if not changed:
        return value

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query_items, doseq=True, safe="<>"),
            parsed.fragment,
        )
    )


# ── Natural-language LLM output sanitization ─────────────────────
# Key-based recursive rules would false-positive on conversational text that
# merely mentions words like "token". LLM response text instead gets narrow
# pattern-based redaction: only explicit KEY=value secret assignments, bearer
# headers, and URL query credentials.

_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)\s*=\s*(\S+)"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9._~+/-]{8,}=*)")
_URL_RE = re.compile(r"\bhttps?://\S+")


def sanitize_llm_text(text: str) -> str:
    """Sanitize free-form LLM output without harming normal conversation.

    Redacts only content with explicit secret shape: env-style assignments
    (``API_KEY=...``), bearer credentials, and sensitive URL query params.
    Plain mentions of words like "token" are preserved.
    """
    if not text:
        return text
    clean = _SECRET_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
    clean = _BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", clean)
    clean = _URL_RE.sub(lambda m: _sanitize_url_query(m.group(0)), clean)
    return clean
