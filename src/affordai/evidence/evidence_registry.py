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
    method: str = "deterministic"  # deterministic | llm


class EvidenceError(Exception):
    pass


class EvidenceRegistry:
    def __init__(self) -> None:
        self._facts: list[Evidence] = []

    def add(self, fact: Evidence, request_id: str, user_id: str) -> None:
        """Accept a fact only if it belongs to this request/user context."""
        if not fact.source_type or not fact.source_id:
            raise EvidenceError("evidence without source identity rejected")
        if fact.request_id is not None and fact.request_id != request_id:
            raise EvidenceError(
                f"evidence {fact.source_id} belongs to {fact.request_id}, "
                f"not {request_id}: rejected"
            )
        if fact.user_id is not None and fact.user_id != user_id:
            raise EvidenceError(
                f"evidence {fact.source_id} belongs to user {fact.user_id}: rejected"
            )
        if not (Decimal("0") <= fact.confidence <= Decimal("1")):
            raise EvidenceError(f"evidence {fact.source_id}: bad confidence")
        self._facts.append(fact)

    def facts_for(self, request_id: str, kinds: set[str] | None = None) -> list[Evidence]:
        out = [f for f in self._facts if f.request_id in (None, request_id)]
        if kinds is not None:
            out = [f for f in out if f.kind in kinds]
        return out

    def __len__(self) -> int:
        return len(self._facts)
