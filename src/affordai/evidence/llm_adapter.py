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

No provider SDK is vendored; the backend hook is explicit so a future
metered run can plug one in without touching the pipeline.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal

from affordai.evidence.evidence_registry import Evidence


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


def _validate_proposal(raw: dict) -> Evidence | None:
    """Strict schema gate: reject anything malformed (fail closed)."""
    try:
        allowed = {
            "cancel",
            "settle",
            "amend_amount",
            "amend_date",
            "delay",
            "confirm",
            "amount",
            "preference",
        }
        if raw.get("kind") not in allowed:
            return None
        if not raw.get("source_id"):
            return None
        conf = Decimal(str(raw.get("confidence", "0")))
        if not (Decimal("0") <= conf <= Decimal("1")):
            return None
        return Evidence(
            source_type=str(raw.get("source_type", "message")),
            source_id=str(raw.get("source_id", "")),
            request_id=raw.get("request_id"),
            user_id=raw.get("user_id"),
            event_id=raw.get("event_id"),
            message_id=raw.get("message_id"),
            image_id=raw.get("image_id"),
            kind=raw["kind"],
            raw_value=str(raw.get("raw_value", ""))[:500],
            normalized_value=str(raw.get("normalized_value", ""))[:200],
            confidence=conf,
            method="llm",
        )
    except Exception:
        return None


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
    # Backend hook: a future metered run plugs a provider call in here with
    # timeout=config.timeout_s, retries=config.max_retries, then passes each
    # raw proposal through _validate_proposal + min_confidence filtering.
    return AdapterResult(facts=[], calls=0, fallback_reason="no-backend")
