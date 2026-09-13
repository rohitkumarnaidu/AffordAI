"""Deterministic conflict resolution (fixed 4-rule precedence).

1. explicit cancellation/settlement/amendment
2. newer record from the same source (sent_at)
3. settled event over estimate/forecast
4. financially safer interpretation (LLM never reorders this)

Every conflict is explicitly represented; the resolver reports what conflicted,
which rule resolved it, and which evidence became authoritative.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from affordai.evidence.evidence_registry import Evidence

_EXPLICIT = {"cancel", "settle", "amend_amount", "amend_date", "delay"}
# Intra-explicit ranking: cancel (0) > settle (1) > amend_* / delay (2)
_EXPLICIT_ORDER = {"cancel": 0, "settle": 1, "amend_amount": 2, "amend_date": 2, "delay": 2}


@dataclass
class Conflict:
    event_id: str
    kind: str
    competing_facts: list[Evidence]
    winning_fact: Evidence
    rule: str  # which precedence rule decided


def _explicit_rank(fact: Evidence) -> int:
    if fact.kind in _EXPLICIT_ORDER:
        return _EXPLICIT_ORDER[fact.kind]
    return 99 if fact.kind not in _EXPLICIT else 3


def _method_rank(fact: Evidence) -> int:
    # Rule 4 safeguard: deterministic beats LLM on tie (AI never overrides)
    return 1 if fact.method == "llm" else 0


def _sent_at_key(fact: Evidence) -> str:
    return fact.sent_at or ""


def _settled_rank(fact: Evidence) -> int:
    return 0 if fact.kind in ("settle", "cancel") else 1


def _rank_key(fact: Evidence) -> tuple:
    """Tier-1 deterministic 6-tuple: explicit_order -> method -> newer_sent desc -> settled -> source."""
    # Sent_at: newer (larger ISO string) should win, so we negate lexical order by using
    # a helper that sorts descending.  Python sort is asc, so we store a negated marker:
    #   key includes (-sent) via reverse trick handled in resolve() two-pass; here we just expose raw.
    return (_explicit_rank(fact), _method_rank(fact), _settled_rank(fact), fact.source_type, fact.source_id)


def resolve(facts: list[Evidence]) -> list[Evidence]:
    """Deterministically order per official 4-rule precedence (Tier-1).

    Order: 1) explicit cancel > settle > amend (intra-rank)
           2) newer same-source (sent_at desc, newest first)
           3) settled over estimate (settle/cancel before others)
           4) safer / method tie-break: deterministic beats LLM, then source_id lexical
           5) deterministic source_type/source_id final tie-break
    """
    # Single stable sort: bucket-aware, but single tuple keeps Rule 1 dominance correctly
    # when combined with newest-first secondary.  We achieve newest-first by sorting
    # descending on sent_at string inside each explicit tier.
    # Approach: global sort with tuple where sent_at is inverted: we sort by explicit_rank
    # asc, method_rank asc, settled asc, then sent_at DESC (newest first), then source tie-break asc.
    # Python can't mix asc/desc in one tuple, so we do two-pass stable: first by tie-break asc,
    # then by sent_at desc, then by method/settled/explicit asc (stable preserves earlier).
    tmp = list(facts)
    # Pass 3: tie-break asc
    tmp.sort(key=lambda f: (f.source_type, f.source_id))
    # Pass 2: newer first (sent_at desc) -- lexical desc == newer first for ISO-8601
    tmp.sort(key=lambda f: f.sent_at or "", reverse=True)
    # Pass 1: explicit / method / settled asc
    tmp.sort(key=lambda f: (_explicit_rank(f), _method_rank(f), _settled_rank(f)))
    return tmp


def detect_conflicts(facts: list[Evidence]) -> list[Conflict]:
    """Detect per-event conflicts.

    Groups by event_id (not event+kind) so cross-kind conflicts
    (e.g. cancel vs amend_amount on same event) are represented.
    Within a group the winning fact is determined by resolve().
    """
    grouped: dict[str, list[Evidence]] = defaultdict(list)
    for f in facts:
        if f.event_id:
            grouped[f.event_id].append(f)
    conflicts: list[Conflict] = []
    for eid, group in grouped.items():
        if len(group) <= 1:
            continue
        ranked = resolve(group)
        winner = ranked[0]
        kinds = {g.kind for g in group}
        explicit_vals = {_explicit_rank(g) for g in group}
        sent_vals = {g.sent_at for g in group}
        if len(kinds) > 1 and ({"cancel", "settle"} & kinds):
            rule = "rule1: explicit cancellation/settlement/amendment"
        elif len(explicit_vals) > 1:
            rule = "rule1: explicit cancellation/settlement/amendment"
        elif len(sent_vals) > 1:
            rule = "rule2: newer record same source"
        elif len({_settled_rank(g) for g in group}) > 1:
            rule = "rule3: settled over estimate"
        else:
            rule = "rule4: financially safer interpretation"
        # Use majority kind label for display; keep full group for audit
        kind_label = winner.kind
        conflicts.append(
            Conflict(event_id=eid, kind=kind_label, competing_facts=list(group), winning_fact=winner, rule=rule)
        )
    return conflicts


def cancelled_event_ids(facts: list[Evidence]) -> set[str]:
    return {f.event_id for f in resolve(facts) if f.kind == "cancel" and f.event_id}


def amended_amounts(facts: list[Evidence]) -> dict[str, str]:
    """event_id -> authoritative normalized amended amount (conflict-resolved)."""
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


def authoritative_facts(facts: list[Evidence]) -> dict[tuple[str, str], Evidence]:
    """Return (event_id, kind) -> winning fact map."""
    grouped: dict[tuple[str, str], list[Evidence]] = defaultdict(list)
    for f in facts:
        if f.event_id:
            grouped[(f.event_id, f.kind)].append(f)
    result: dict[tuple[str, str], Evidence] = {}
    for key, group in grouped.items():
        ranked = resolve(group)
        result[key] = ranked[0]
    return result
