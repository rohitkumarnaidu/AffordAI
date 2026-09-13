"""Centralized secret redaction for ALL logging/tracing/telemetry.

Contract (Sec 31.3):
- No log/trace/usage-report/artifact may contain raw API keys, tokens,
  passwords, authorization headers, cookies, or private credentials.
- Callers MUST pass log text through `redact()` before emitting.
- `sanitize_mapping()` scrubs dict payloads (env snapshots, usage records).

Patterns are deliberately broad (fail-closed): any `KEY=`-style assignment
with a non-empty value is redacted unless the value is an obvious
placeholder (empty, `your_*`, `placeholder`, `example`, `***`, `xxx`).

Single source of truth -- no duplicate redaction logic elsewhere.
"""
from __future__ import annotations

import re

_REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = (
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "client_secret",
    "access_token",
    "auth_token",
    "authorization",
    "bearer",
    "password",
    "passwd",
    "private_key",
    "cookie",
    "session_token",
    "openai_api_key",
    "anthropic_api_key",
    "google_api_key",
)

_PLACEHOLDER_VALUES = frozenset({"", "none", "null", "nil", "-", "***", "xxx", "test", "example"})


def _is_placeholder(value: str) -> bool:
    low = value.strip().lower().strip("[]")
    if low in _PLACEHOLDER_VALUES:
        return True
    if low == "redacted" or low == "[redacted]":
        return True
    if low.startswith("your_"):
        return True
    if "placeholder" in low or "example" in low or "here" in low:
        return True
    if low == "[redacted]":
        return True
    return False


_ASSIGN_RE = re.compile(
    r"(?i)(api_key|apikey|api-key|secret|client_secret|access_token|auth_token|"
    r"authorization|bearer|password|passwd|private_key|cookie|session_token|"
    r"openai_api_key|anthropic_api_key|google_api_key)"
    r"(\s*[:=]\s*)([\"']?)([^\s\"'`,;\n]{1,200})"
)

_BARE_RE = re.compile(
    r"(sk-ant-[A-Za-z0-9_\-]{8,}|sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{8,}|"
    r"gho_[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{16}|xox[bpas]-[A-Za-z0-9\-]{8,}|"
    r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)"
)


def redact(text: str) -> str:
    """Redact sensitive values in free text. Never raises."""
    try:
        if not isinstance(text, str):
            text = str(text)

        def _sub_assign(m: re.Match) -> str:
            value = m.group(4)
            if _is_placeholder(value):
                return m.group(0)
            return f"{m.group(1)}{m.group(2)}{m.group(3)}{_REDACTED}"

        out = _ASSIGN_RE.sub(_sub_assign, text)
        out = _BARE_RE.sub(_REDACTED, out)
        return out
    except Exception:
        return _REDACTED


def sanitize_mapping(mapping: dict) -> dict:
    """Return a copy of `mapping` with sensitive VALUES redacted. Never raises."""
    try:
        clean: dict = {}
        for key, value in dict(mapping).items():
            low_key = str(key).lower().replace("-", "_")
            if any(s in low_key for s in _SENSITIVE_KEYS):
                if isinstance(value, str) and _is_placeholder(value):
                    clean[key] = value
                else:
                    clean[key] = _REDACTED
            elif isinstance(value, str):
                clean[key] = redact(value)
            elif isinstance(value, dict):
                clean[key] = sanitize_mapping(value)
            else:
                clean[key] = value
        return clean
    except Exception:
        return {}


def contains_secret(text: str) -> bool:
    """True if `text` appears to hold an unredacted secret (tests/scans)."""
    try:
        if _BARE_RE.search(text):
            return True
        for m in _ASSIGN_RE.finditer(text):
            if not _is_placeholder(m.group(4)):
                return True
        return False
    except Exception:
        return True
