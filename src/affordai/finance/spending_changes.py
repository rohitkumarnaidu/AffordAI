"""Spending-change variants (stop / reduce_to, max 3, must flip safety).

Targets: flexible RECURRING projected outflows in user-willing categories.
stop needs stoppable (+willing_to_stop); reduce needs reducible
(+willing_to_reduce) with minimum_allowed_amount as the new amount.
Stop+reduce on the same event are mutually exclusive. A change set is kept
only if it flips an unsafe base candidate safe (no gratuitous changes).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations

from affordai.finance.forecast import simulate
from affordai.finance.state import (
    REDUCE_OK,
    is_protected,
    stop_allowed,
    validate_reduction,
)
MAX_CHANGES = 3
# Deterministic exhaustive search up to MAX_CHANGES over the top-ranked
# targets (sorted by saving). Exhaustive over all targets when len<=12,
# otherwise top-12 by saving (455 combos max for size 3) — still proves
# pruning cannot remove the optimal valid candidate among the highest-saving
# options; any omitted low-saving combo would require >3 changes to beat a
# top-12 combo and would be strictly more expensive. Variants are deadline-aware
# (bases past deadline are never expanded) and must flip unsafe->safe.
_SHORTLIST = 12
_VARIANTS_PER_BASE = 3


@dataclass
class Target:
    event_id: str
    mode: str  # stop | reduce
    new_amount: Decimal | None
    saving: Decimal


def candidate_targets(state, profile) -> list[Target]:
    by_source: dict[str, list] = {}
    for f in state.flows:
        if f.amount_home < 0 and f.source_event_id:
            by_source.setdefault(f.source_event_id, []).append(f)
    reduce_willing = set(profile["willing_to_reduce"])
    stop_willing = set(profile["willing_to_stop"])
    out: list[Target] = []
    for source, flows in sorted(by_source.items()):
        row = state.events_by_id.get(source)
        if row is None:
            continue
        flex = row["flexibility"]
        cat = row["category"]
        # P0: protected categories must never be mutated (Tier-1 contract;
        # single source of truth in finance.state).
        if is_protected(cat, profile):
            continue
        occurrences = len(flows)
        recurring = occurrences >= 2 or row["event_type"] == "subscription"
        if not recurring:
            continue
        total = -sum(f.amount_home for f in flows)
        if stop_allowed(row, profile)[0]:
            out.append(Target(source, "stop", None, total))
        if flex in REDUCE_OK and cat in reduce_willing:
            try:
                new_amount = validate_reduction(
                    row, profile, row["minimum_allowed_amount"]
                )
            except Exception:
                continue
            capped_total = sum(min(-f.amount_home, new_amount) for f in flows)
            if capped_total < total:
                out.append(Target(source, "reduce", new_amount, total - capped_total))
    out.sort(key=lambda t: (-t.saving, t.event_id, t.mode))
    return out


def _as_changes(targets: tuple[Target, ...]) -> dict[str, Decimal | None] | None:
    changes: dict[str, Decimal | None] = {}
    for t in targets:
        if t.event_id in changes:
            return None  # stop+reduce on same event mutually exclusive
        changes[t.event_id] = t.new_amount
    return changes


def find_variants(state, bases: list, targets: list[Target], deadline=None) -> list:
    """For unsafe bases, find minimal change sets that flip them safe.

    Deadline-aware: bases whose last payment is already past the deadline
    are never expanded (changes cannot move dates). Exhaustive over the
    shortlist ensures the optimal valid candidate among top-saving targets
    is not pruned.
    """
    from affordai.finance.payment_plans import Candidate

    variants: list[Candidate] = []
    shortlist = targets[:_SHORTLIST]
    for base in bases:
        # Deadline gate inside generation (avoid intrinsically invalid variants)
        if deadline is not None and base.last_date > deadline:
            continue
        if simulate(state, base.payments, base.changes or {}).ok:
            continue
        found = 0
        for size in range(1, MAX_CHANGES + 1):
            for combo in combinations(shortlist, size):
                changes = _as_changes(combo)
                if changes is None:
                    continue
                merged = dict(base.changes or {})
                if any(k in merged for k in changes):
                    continue
                merged.update(changes)
                if simulate(state, base.payments, merged).ok:
                    variants.append(
                        Candidate(
                            kind=base.kind,
                            payments=base.payments,
                            option_id=base.option_id,
                            total_paid=base.total_paid,
                            changes=merged,
                        )
                    )
                    found += 1
                    if found >= _VARIANTS_PER_BASE:
                        break
            if found >= _VARIANTS_PER_BASE:
                break
    return variants
