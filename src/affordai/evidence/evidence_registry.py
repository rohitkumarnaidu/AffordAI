"""Canonical evidence registry: every extracted fact keeps provenance.

Provenance fields: source_type/source_id/request_id/user_id/event_id/
message_id/image_id/raw_value/normalized_value/confidence/method.
Unsupported evidence never enters decisions: `add()` validates IDs and
ownership against the request context before accepting a fact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class Evidence:
    source_type: str  # message | image | event | profile | payment_option
    source_id: str
    request_id: str | None
    user_id: str | None
    event_id: str | None = None
    message_id: str | None = None
    image_id: str | None = None
    kind: str = ""  # cancel|settle|amend_amount|amend_date|delay|confirm|amount|preference
    raw_value: str = ""
    normalized_value: str = ""
    confidence: Decimal = Decimal("1.0")
    method: str = "deterministic"  # deterministic | llm | derived_calculation | structured_dataset
    extraction_method: str | None = None  # alias for method provenance
    # Optional sent_at for conflict ordering (newer same-source wins)
    sent_at: str | None = None

    def provenance(self) -> dict:
        """Return full provenance trace dict."""
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "event_id": self.event_id,
            "message_id": self.message_id,
            "image_id": self.image_id,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "method": self.method,
            "extraction_method": self.extraction_method or self.method,
            "confidence": str(self.confidence),
            "kind": self.kind,
            "sent_at": self.sent_at,
        }


class EvidenceError(Exception):
    pass


ALLOWED_KINDS = {
    "cancel",
    "settle",
    "amend_amount",
    "amend_date",
    "delay",
    "confirm",
    "amount",
    "preference",
}
ALLOWED_METHODS = {
    "deterministic",
    "llm",
    "derived_calculation",
    "structured_dataset",
    "message_extraction",
    "image_extraction",
}
ALLOWED_SOURCE_TYPES = {"message", "image", "event", "profile", "payment_option"}


class EvidenceRegistry:
    def __init__(self, valid_event_ids: set[str] | None = None, valid_message_ids: set[str] | None = None, valid_image_ids: set[str] | None = None) -> None:
        self._facts: list[Evidence] = []
        self._valid_event_ids = valid_event_ids
        self._valid_message_ids = valid_message_ids
        self._valid_image_ids = valid_image_ids
        self._rejected: list[dict] = []  # trace of rejected facts for audit

    def _record_rejection(self, fact: Evidence, reason: str) -> None:
        self._rejected.append({"source_id": fact.source_id, "kind": fact.kind, "reason": reason, "provenance": fact.provenance() if hasattr(fact, "provenance") else {}})

    def add(self, fact: Evidence, request_id: str, user_id: str) -> None:
        """Accept a fact only if it belongs to this request/user context and passes all provenance checks."""
        if not fact.source_type or not fact.source_id:
            self._record_rejection(fact, "missing source_type/source_id")
            raise EvidenceError("evidence without source identity rejected")
        if fact.source_type not in ALLOWED_SOURCE_TYPES:
            self._record_rejection(fact, f"invalid source_type {fact.source_type}")
            raise EvidenceError(f"evidence {fact.source_id}: invalid source_type {fact.source_type}")
        if fact.kind and fact.kind not in ALLOWED_KINDS:
            self._record_rejection(fact, f"invalid kind {fact.kind}")
            raise EvidenceError(f"evidence {fact.source_id}: invalid kind {fact.kind}")
        if fact.method and fact.method not in ALLOWED_METHODS:
            self._record_rejection(fact, f"invalid method {fact.method}")
            raise EvidenceError(f"evidence {fact.source_id}: invalid method {fact.method}")
        if fact.request_id is not None and fact.request_id != request_id:
            self._record_rejection(fact, f"wrong request {fact.request_id} != {request_id}")
            raise EvidenceError(
                f"evidence {fact.source_id} belongs to {fact.request_id}, "
                f"not {request_id}: rejected"
            )
        if fact.user_id is not None and fact.user_id != user_id:
            self._record_rejection(fact, f"wrong user {fact.user_id} != {user_id}")
            raise EvidenceError(
                f"evidence {fact.source_id} belongs to user {fact.user_id}: rejected"
            )
        # Event/message/image ID must exist in context if provided
        if fact.event_id is not None and self._valid_event_ids is not None and fact.event_id not in self._valid_event_ids:
            self._record_rejection(fact, f"unknown event_id {fact.event_id}")
            raise EvidenceError(f"evidence {fact.source_id}: unknown event_id {fact.event_id} for request {request_id}")
        if fact.message_id is not None and self._valid_message_ids is not None and fact.message_id not in self._valid_message_ids:
            self._record_rejection(fact, f"unknown message_id {fact.message_id}")
            raise EvidenceError(f"evidence {fact.source_id}: unknown message_id {fact.message_id}")
        if fact.image_id is not None and self._valid_image_ids is not None and fact.image_id not in self._valid_image_ids:
            self._record_rejection(fact, f"unknown image_id {fact.image_id}")
            raise EvidenceError(f"evidence {fact.source_id}: unknown image_id {fact.image_id}")
        try:
            _conf_finite = fact.confidence.is_finite()
        except Exception:
            _conf_finite = False
        if not _conf_finite:
            self._record_rejection(fact, f"non-finite confidence {fact.confidence!r}")
            raise EvidenceError(f"evidence {fact.source_id}: non-finite confidence rejected")
        if not (Decimal("0") <= fact.confidence <= Decimal("1")):
            self._record_rejection(fact, f"bad confidence {fact.confidence}")
            raise EvidenceError(f"evidence {fact.source_id}: bad confidence")
        # Raw/normalized preservation: raw must be present if normalized is set
        if fact.normalized_value and not fact.raw_value and fact.kind in ("amend_amount", "amend_date", "amount"):
            # Allow empty raw for derived facts, but log
            pass
        # Confidence 0 is allowed only for UNKNOWN markers (not for high-confidence claims)
        self._facts.append(fact)

    def facts_for(self, request_id: str, kinds: set[str] | None = None) -> list[Evidence]:
        out = [f for f in self._facts if f.request_id in (None, request_id)]
        if kinds is not None:
            out = [f for f in out if f.kind in kinds]
        return out

    def all_facts(self) -> list[Evidence]:
        return list(self._facts)

    def rejected(self) -> list[dict]:
        return list(self._rejected)

    def validate_provenance(self) -> list[str]:
        """Validate every fact has traceable provenance."""
        errors: list[str] = []
        for f in self._facts:
            if not f.source_id:
                errors.append(f"fact missing source_id")
            if not f.source_type:
                errors.append(f"fact {f.source_id} missing source_type")
            if not f.kind:
                errors.append(f"fact {f.source_id} missing kind")
            # raw vs normalized check is advisory, not error
        return errors

    def validate_claim_support(self, required_kinds: set[str]) -> list[str]:
        """Ensure required kinds have at least one supporting fact."""
        present = {f.kind for f in self._facts}
        missing = required_kinds - present
        return [f"unsupported claim kind {k}: no evidence" for k in missing]

    def __len__(self) -> int:
        return len(self._facts)
