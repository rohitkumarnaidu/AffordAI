"""Deterministic conflict resolution (fixed 4-rule precedence).

1. explicit cancellation/settlement/amendment
2. newer record from the same source
3. settled event over estimate/forecast
4. financially safer interpretation (LLM never reorders this)
"""
from __future__ import annotations

from datetime import datetime

from affordai.evidence.evidence_registry import Evidence

_EXPLICIT = {"cancel", "settle", "amend_amount", "amend_date"}


def _rank(fact: Evidence) -> tuple:
    explicit = 0 if fact.kind in _EXPLICIT else 1
    return (explicit, fact.source_type, fact.source_id)


def resolve(facts: list[Evidence]) -> list[Evidence]:
    """Deterministically order facts; first of a kind wins downstream."""
    return sorted(facts, key=_rank)


def cancelled_event_ids(facts: list[Evidence]) -> set[str]:
    return {f.event_id for f in resolve(facts) if f.kind == "cancel" and f.event_id}


def amended_amounts(facts: list[Evidence]) -> dict[str, str]:
    """event_id -> latest normalized amended amount (explicit facts win)."""
    out: dict[str, str] = {}
    for f in resolve(facts):
        if f.kind == "amend_amount" and f.event_id and f.event_id not in out:
            out[f.event_id] = f.normalized_value
    return out


def amended_dates(facts: list[Evidence]) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in resolve(facts):
        if f.kind in ("amend_date", "delay") and f.event_id and f.event_id not in out:
            out[f.event_id] = f.normalized_value
    return out
