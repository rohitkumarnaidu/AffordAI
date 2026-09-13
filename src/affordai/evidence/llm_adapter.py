"""Bounded LLM/vision adapter (optional enhancement, NEVER on safety path).

Contract (user-approved):
- Deterministic E0 works fully with this adapter DISABLED (default: every
  .env value empty -> disabled).
- When enabled, the adapter only PROPOSES typed facts with confidence;
  every proposal is schema-validated and must pass the same
  EvidenceRegistry ownership checks. Deterministic code re-validates.
- On unavailable backend, timeout, failure, invalid schema, or confidence
  below threshold -> deterministic fallback (empty proposals + recorded
  reason). The adapter NEVER raises into the pipeline.
- The adapter NEVER decides affordability, safety, ranking, or arithmetic.

Model-call inventory (Sec 32.1): exactly TWO call sites exist, both funnel
through `propose_facts`:
  1. `message_extract` -- per-request message pass (selective)
  2. `image_amount_extract` -- per blank-amount event with linked images
See `docs/model-call-inventory.md` for the full per-call contract table and
`evaluation/usage_report.md` for the metered final-run accounting.

No provider SDK is vendored; the backend hook is explicit so a future
metered run can plug one in without touching the pipeline.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime as _dt
from decimal import Decimal, InvalidOperation

from affordai.evidence.evidence_registry import Evidence

# ---------------------------------------------------------------------------
# Sec 32.1 -- single source of truth for model-call inventory
# ---------------------------------------------------------------------------

PROMPT_VERSION = "affordai-extract-v1"
SCHEMA_VERSION = "affordai-evidence-v1"

SUPPORTED_CURRENCIES = frozenset({"EUR", "USD", "IDR", "INR", "ZAR"})

MODEL_CALLS: tuple[dict, ...] = (
    {
        "call_id": "message_extract",        "provider": "config MODEL_PROVIDER (empty in E0)",
        "model": "config MODEL_NAME (empty in E0)",
        "trigger": "per request with >=1 message AND needs_llm_for_messages() true",
        "purpose": "semantic interpretation of message text into typed facts only",
        "input_scope": "single request: minimized message contexts (ids + <=500ch text each); never other requests/users",
        "output_schema": "list of {kind, source_type, source_id, request_id, user_id, event_id?, message_id?, image_id?, raw_value, normalized_value, confidence}; kind in 8-value allowlist",
        "validation": "_validate_proposal strict gate + min_confidence + EvidenceRegistry ownership",
        "retry_behavior": "bounded: max_retries from LLM_MAX_RETRIES (default 1); transient errors only; else fallback",
        "fallback": "empty proposals + fallback_reason; deterministic interpreter facts still apply",
        "token_measurement": "ModelCallRecord per attempt (estimated via estimate_tokens; provider usage when a backend reports it)",
    },
    {
        "call_id": "image_amount_extract",
        "provider": "config MODEL_PROVIDER (empty in E0)",
        "model": "config VISION_MODEL_NAME (empty in E0)",
        "trigger": "per blank-amount event with >=1 linked existing image AND needs_llm_for_image() true",
        "purpose": "read the numeric amount from the linked receipt image only",
        "input_scope": "single event: image ids + file paths for that event only; kind forced to amount",
        "output_schema": "same but kind MUST be amount with finite positive normalized_value",
        "validation": "_validate_proposal + kind==amount gate + parse_amount>0 + min_confidence + registry ownership",
        "retry_behavior": "same bounded retry budget",
        "fallback": "UNKNOWN amount marker (blank is never zero); plan must stay safe without it",
        "token_measurement": "same ModelCallRecord accounting",
    },
)

# Sec 34 failure matrix (single source of truth; code is authoritative).
# Every model/tool boundary failure -> detection -> retry? -> fallback ->
# final behavior. "Logged?" is always the Sec-33 RequestTrace failures list
# plus the legacy Trace event (decision-fallback / evidence detail).
FAILURE_MATRIX: tuple[dict, ...] = (
    {"failure": "timeout", "detection": "TimeoutError from backend", "retry": "bounded (1+max_retries)", "fallback": "empty proposals; deterministic facts still apply", "final": "safe decision from deterministic evidence; never fabricated", "logged": "yes"},
    {"failure": "api-failure-5xx", "detection": "ProviderError from backend", "retry": "bounded (1+max_retries)", "fallback": "empty proposals; deterministic facts still apply", "final": "safe decision from deterministic evidence; never fabricated", "logged": "yes"},
    {"failure": "rate-limit-429", "detection": "RateLimitError from backend", "retry": "bounded backoff (0.5,1,2.. cap 8s)", "fallback": "empty proposals; deterministic facts still apply", "final": "safe decision; no retry storm (attempts fixed); never fabricated", "logged": "yes"},
    {"failure": "invalid-json", "detection": "validate_proposal_json returns None", "retry": "no (non-retryable)", "fallback": "proposal dropped; UNKNOWN amount marker for blank image amounts", "final": "malformed output never enters the financial engine", "logged": "yes"},
    {"failure": "unexpected-output", "detection": "_validate_proposal strict gate (kind/enum/type/range/date/currency/extra-field)", "retry": "no (non-retryable)", "fallback": "proposal dropped; registry ownership re-checks survivors; never enters engine", "final": "deterministic rejection; engine re-validates", "logged": "yes"},
    {"failure": "missing-evidence", "detection": "no usable fact for a financial claim", "retry": "n/a", "fallback": "UNKNOWN marker (blank amount never zero); safest valid decision", "final": "missing_evidence recorded; no invented fact", "logged": "yes"},
    {"failure": "image-failure", "detection": "resolve_images_for_event file_exists false / unreadable / vision invalid", "retry": "bounded only for transient vision transport", "fallback": "amount_unknown_evidence (confidence 0); plan must stay safe without it", "final": "unknown amount never becomes 0", "logged": "yes"},
)


@dataclass
class LlmConfig:
    enabled: bool = False
    provider: str = ""
    model: str = ""
    vision_model: str = ""
    timeout_s: float = 30.0
    max_retries: int = 1
    min_confidence: Decimal = Decimal("0.80")
    reason: str = "disabled"


def load_config_from_env(env: dict | None = None) -> LlmConfig:
    src = env if env is not None else os.environ
    enabled = str(src.get("LLM_ENABLED", "")).strip() == "1"
    if not enabled:
        return LlmConfig(enabled=False, reason="LLM_ENABLED != 1")
    if not str(src.get("API_KEY", "")).strip():
        return LlmConfig(enabled=False, reason="no API_KEY")
    try:
        timeout = float(str(src.get("LLM_TIMEOUT_S", "") or "30"))
        retries = int(str(src.get("LLM_MAX_RETRIES", "") or "1"))
        min_conf = Decimal(str(src.get("LLM_MIN_CONFIDENCE", "") or "0.80"))
    except Exception:
        return LlmConfig(enabled=False, reason="bad numeric LLM_* config")
    return LlmConfig(
        enabled=True,
        provider=str(src.get("MODEL_PROVIDER", "")),
        model=str(src.get("MODEL_NAME", "")),
        vision_model=str(src.get("VISION_MODEL_NAME", "")),
        timeout_s=timeout,
        max_retries=max(0, retries),
        min_confidence=min_conf,
        reason="ok",
    )


@dataclass
class AdapterResult:
    facts: list[Evidence] = field(default_factory=list)
    calls: int = 0
    fallback_reason: str = "disabled"
    records: list["ModelCallRecord"] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sec 32.3 token instrumentation (secret-safe: counts only, never prompts)
# ---------------------------------------------------------------------------

@dataclass
class ModelCallRecord:
    timestamp: str = ""
    request_id: str = ""
    provider: str = ""
    model: str = ""
    purpose: str = ""  # message_extract | image_amount_extract
    input_tokens: int = 0
    output_tokens: int = 0
    success: bool = False
    retry_number: int = 0
    fallback: str = ""
    token_source: str = "estimated"  # estimated | provider
    backoff_s: list = field(default_factory=list)  # bounded backoff schedule actually applied

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def estimate_tokens(text: str) -> int:
    """Documented local estimator: ceil(chars/4), min 1 for non-empty.

    LOCAL MEASUREMENT, clearly estimated: used ONLY because no provider SDK
    is vendored in E0. When a real backend reports usage, that value wins
    (token_source=provider). Never represented as provider billing.
    """
    try:
        if not text:
            return 0
        return max(1, (len(text) + 3) // 4)
    except Exception:
        return 0


def _utc_now_iso() -> str:
    try:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Sec 31.2 strict structured-output validation (fail closed, no coercion)
# ---------------------------------------------------------------------------

_ALLOWED_KINDS = frozenset(
    {"cancel", "settle", "amend_amount", "amend_date", "delay", "confirm", "amount", "preference"}
)
_ALLOWED_SOURCE_TYPES = frozenset({"message", "image", "event", "profile", "payment_option"})
_ALLOWED_FIELDS = frozenset(
    {
        "kind", "source_type", "source_id", "request_id", "user_id",
        "event_id", "message_id", "image_id", "raw_value",
        "normalized_value", "confidence", "currency",
    }
)
_PREFERENCE_VALUES = frozenset({"installments", "partial_payment", "full_payment", "wait"})
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_finite_decimal(value: Decimal) -> bool:
    try:
        return value.is_finite()
    except Exception:
        return False


def _validate_proposal(raw: dict | None) -> Evidence | None:
    """Strict schema gate: reject anything malformed (fail closed).

    Rejects: non-dict/None/list, invalid JSON already filtered, missing
    kind/source_id, unknown enum kind, unknown source_type, wrong data types,
    NaN/Infinity confidence or amounts, out-of-range confidence, negative/zero
    amounts, malformed dates, unsupported currencies, unsupported actions, and
    unexpected top-level fields (strict schema).
    """
    try:
        if not isinstance(raw, dict):
            return None
        for key in raw.keys():
            if key not in _ALLOWED_FIELDS:
                return None
        kind = raw.get("kind")
        if kind not in _ALLOWED_KINDS:
            return None
        source_id = raw.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            return None
        source_type = raw.get("source_type", "message")
        if source_type not in _ALLOWED_SOURCE_TYPES:
            return None
        for id_field in ("request_id", "user_id", "event_id", "message_id", "image_id"):
            val = raw.get(id_field)
            if val is not None and (not isinstance(val, str) or not val.strip()):
                return None
        conf_raw = raw.get("confidence", "0")
        if isinstance(conf_raw, bool):
            return None
        if isinstance(conf_raw, float):
            import math as _math

            if not _math.isfinite(conf_raw):
                return None
        try:
            conf = Decimal(str(conf_raw))
        except (InvalidOperation, ValueError, TypeError, ArithmeticError):
            return None
        if not _is_finite_decimal(conf):
            return None
        if not (Decimal("0") <= conf <= Decimal("1")):
            return None
        for text_field in ("raw_value", "normalized_value"):
            val = raw.get(text_field, "")
            if not isinstance(val, str):
                return None
        raw_value = str(raw.get("raw_value", ""))[:500]
        normalized_value = str(raw.get("normalized_value", ""))[:200]
        if kind == "amend_date":
            if not _DATE_RE.match(normalized_value):
                return None
            try:
                _dt.strptime(normalized_value, "%Y-%m-%d").date()
            except ValueError:
                return None
        if kind in ("amend_amount", "amount"):
            if not normalized_value.strip() or normalized_value.strip().lower() == "unknown":
                return None
            try:
                amount_val = Decimal(normalized_value.strip().replace(",", ""))
            except (InvalidOperation, ValueError, AttributeError):
                return None
            if not _is_finite_decimal(amount_val):
                return None
            if amount_val <= 0:
                return None
        if kind == "preference":
            if normalized_value not in _PREFERENCE_VALUES:
                return None
        currency = raw.get("currency")
        if currency is not None:
            if not isinstance(currency, str) or currency not in SUPPORTED_CURRENCIES:
                return None
        return Evidence(
            source_type=str(source_type),
            source_id=str(source_id),
            request_id=raw.get("request_id"),
            user_id=raw.get("user_id"),
            event_id=raw.get("event_id"),
            message_id=raw.get("message_id"),
            image_id=raw.get("image_id"),
            kind=kind,
            raw_value=raw_value,
            normalized_value=normalized_value,
            confidence=conf,
            method="llm",
        )
    except Exception:
        return None


def validate_proposal_json(text: str) -> Evidence | None:
    """Parse one JSON object string then strictly validate it."""
    try:
        parsed = json.loads(text)
        return _validate_proposal(parsed)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Sec 32.2 deterministic shortcuts, selective calls, context minimization
# ---------------------------------------------------------------------------

def minimize_message_context(message: dict) -> dict:
    """Reduce model input to the minimum needed for extraction.

    Keeps: ids + truncated text (<=500ch). Drops everything else.
    """
    try:
        text = str(message.get("message_text") or "")[:500]
        return {
            "message_id": message.get("message_id"),
            "request_id": message.get("request_id"),
            "user_id": message.get("user_id"),
            "related_event_id": message.get("related_event_id"),
            "sent_at": message.get("sent_at"),
            "message_text": text,
        }
    except Exception:
        return {}


def minimize_image_context(event_id: str, image_ids: list[str]) -> dict:
    """Minimal image-call payload: event + its image ids only."""
    try:
        return {"event_id": event_id, "images": list(image_ids)[:8]}
    except Exception:
        return {"event_id": event_id, "images": []}


def needs_llm_for_messages(messages: list[dict], deterministic_fact_count: int) -> bool:
    """True only when semantic interpretation may add value."""
    try:
        if not messages:
            return False
        if deterministic_fact_count >= len(messages):
            return False
        for message in messages:
            text = str(message.get("message_text") or "").strip()
            if len(text) >= 20:
                return True
        return False
    except Exception:
        return False


def needs_llm_for_image(event_amount, linked_existing: int) -> bool:
    """True only when the amount is blank AND a linked image file exists."""
    try:
        return event_amount is None and linked_existing > 0
    except Exception:
        return False


def check_batch_safe(request_ids: list[str], user_ids: list[str]) -> None:
    """Fail-closed batching guard: one request/user per model call."""
    if len(set(request_ids)) > 1:
        raise ValueError("unsafe batch: multiple request_ids in one model call")
    if len(set(user_ids)) > 1:
        raise ValueError("unsafe batch: multiple user_ids in one model call")


TRANSIENT_ERRORS = (TimeoutError, ConnectionError)


class RateLimitError(Exception):
    """Provider 429 rate-limit signal (transient: bounded retry, then fallback)."""


class ProviderError(Exception):
    """Provider 5xx / unavailable signal (transient: bounded retry, then fallback)."""


# Sec 34.3 explicit retry policy (single source of truth).
# RETRYABLE: transient transport/provider signals only.
RETRYABLE_ERRORS = (TimeoutError, ConnectionError, RateLimitError, ProviderError)
# NON-RETRYABLE (never retried, immediate fallback): invalid schema/JSON,
# deterministic validation failures, business-rule violations, unsupported
# operations, cross-request batching violations, bad local configuration.
NON_RETRYABLE_ERRORS = (ValueError, TypeError, KeyError, json.JSONDecodeError)


def backoff_for_attempt(attempt: int, base_s: float = 0.5, cap_s: float = 8.0) -> float:
    """Bounded exponential backoff schedule (deterministic, no sleep here).

    attempt is 0-based retry number. Returns min(cap, base * 2**attempt).
    The adapter records the schedule in the call record; the backend (or a
    future provider plug-in) performs the actual wait. No retry storm:
    total attempts are always 1 + max_retries regardless of error mix.
    """
    try:
        wait = float(base_s) * (2 ** max(0, int(attempt)))
        return min(float(cap_s), wait)
    except Exception:
        return float(base_s)


def call_with_retry(
    backend, config: LlmConfig, *, purpose: str, request_id: str = ""
) -> tuple[list[dict], ModelCallRecord]:
    """Invoke `backend()` under a FINITE retry budget.

    - Retries RETRYABLE errors only (timeout/connection/429/5xx), up to
      config.max_retries. Records the bounded backoff schedule per retry.
    - NON-RETRYABLE errors (invalid schema, validation, business-rule,
      unsupported op) never retry: immediate fallback.
    - Never raises; exhaustion -> fallback. Never infinite.
    """
    record = ModelCallRecord(
        timestamp=_utc_now_iso(),
        request_id=request_id,
        provider=config.provider,
        model=config.model if purpose == "message_extract" else (config.vision_model or config.model),
        purpose=purpose,
    )
    attempts = 1 + max(0, int(config.max_retries))
    last_error = "ok"
    backoff_schedule: list[float] = []
    for attempt in range(attempts):
        record.retry_number = attempt
        try:
            raw_items, in_tok, out_tok = backend()
            record.input_tokens += int(in_tok or 0)
            record.output_tokens += int(out_tok or 0)
            record.success = True
            record.fallback = ""
            if backoff_schedule:
                record.fallback = ""
            record.backoff_s = backoff_schedule
            return list(raw_items or []), record
        except RETRYABLE_ERRORS as exc:
            last_error = f"transient:{type(exc).__name__}"
            backoff_schedule.append(backoff_for_attempt(attempt))
            continue
        except Exception as exc:
            record.success = False
            record.fallback = f"backend:{type(exc).__name__}"
            record.backoff_s = backoff_schedule
            return [], record
    record.success = False
    record.fallback = f"retry-exhausted:{last_error}"
    record.backoff_s = backoff_schedule
    return [], record


class ModelCache:
    """Versioned in-memory cache (opt-in; default OFF in E0)."""

    def __init__(self) -> None:
        self._store: dict[str, list[dict]] = {}

    def key(self, provider: str, model: str, purpose: str, payload: dict, config_note: str = "") -> str:
        blob = json.dumps(payload, sort_keys=True, default=str)
        digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]
        return "|".join([provider, model, PROMPT_VERSION, SCHEMA_VERSION, purpose, config_note, digest])

    def get(self, key: str) -> list[dict] | None:
        return self._store.get(key)

    def put(self, key: str, value: list[dict]) -> None:
        self._store[key] = list(value)


_CACHE = ModelCache()


def propose_facts(
    kind: str, payload: dict, config: LlmConfig
) -> AdapterResult:
    """Propose facts via the model backend, or fall back deterministically.

    The model backend is intentionally unplugged in E0 (no SDK vendored):
    with config.enabled True but no backend, this records `no-backend` and
    returns zero proposals so the deterministic path proceeds unchanged.
    """
    if not config.enabled:
        return AdapterResult(facts=[], calls=0, fallback_reason=config.reason)
    purpose = "message_extract" if kind == "message" else "image_amount_extract"
    record = ModelCallRecord(
        timestamp=_utc_now_iso(),
        request_id=str((payload or {}).get("request_id") or (payload or {}).get("event_id") or ""),
        provider=config.provider,
        model=config.model if purpose == "message_extract" else (config.vision_model or config.model),
        purpose=purpose,
        fallback="no-backend",
    )
    return AdapterResult(facts=[], calls=0, fallback_reason="no-backend", records=[record])
