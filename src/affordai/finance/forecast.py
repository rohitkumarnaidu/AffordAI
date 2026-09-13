"""90-day daily-ledger forecast + safe-amount / earliest-date search.

Invariant: a plan is safe ONLY if closing >= minimum on EVERY projected
day. Within a day: opening + inflows - outflows - plan payments.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from affordai.finance.money import quantize_money
from affordai.finance.timeline import WINDOW_DAYS

Change = tuple[str, Decimal | None]  # (source_event_id, None=stop | new_amount=reduce cap)


@dataclass
class SimResult:
    ok: bool
    min_closing: Decimal
    worst_day: date | None


def _apply_changes(
    daily_net: dict[date, Decimal],
    flows_by_source: dict[str, list],
    changes: dict[str, Decimal | None],
) -> dict[date, Decimal]:
    """Return adjusted daily net. stop -> remove source outflows; reduce -> cap each occurrence."""
    if not changes:
        return daily_net
    adjusted = dict(daily_net)
    for source, new_amount in changes.items():
        for flow in flows_by_source.get(source, []):
            if flow.amount_home >= 0:
                continue  # changes only cut outflows
            if new_amount is None:
                delta = -flow.amount_home  # add back the outflow
            else:
                capped = -min(-flow.amount_home, new_amount)
                delta = capped - flow.amount_home
            adjusted[flow.day] = adjusted.get(flow.day, Decimal("0")) + delta
    return adjusted


def simulate(
    state,
    payments: list[tuple[date, Decimal]],
    changes: dict[str, Decimal | None] | None = None,
) -> SimResult:
    changes = changes or {}
    flows_by_source: dict[str, list] = {}
    for f in state.flows:
        if f.source_event_id:
            flows_by_source.setdefault(f.source_event_id, []).append(f)
    daily = _apply_changes(state.daily_net, flows_by_source, changes)
    pay_by_day: dict[date, Decimal] = {}
    for day, amount in payments:
        pay_by_day[day] = pay_by_day.get(day, Decimal("0")) + amount
    balance = state.opening
    worst = balance
    worst_day = state.request_date
    for offset in range(WINDOW_DAYS):
        day = state.request_date + timedelta(days=offset)
        balance = balance + daily.get(day, Decimal("0")) - pay_by_day.get(day, Decimal("0"))
        if balance < worst:
            worst = balance
            worst_day = day
        if balance < state.minimum:
            return SimResult(ok=False, min_closing=worst, worst_day=day)
    return SimResult(ok=True, min_closing=worst, worst_day=worst_day)


def max_safe_today(state) -> Decimal:
    """Max single payment safe on request_date (no changes), via minor-unit binary search."""
    unit = Decimal("0.01")
    hi = int((state.requested / unit).to_integral_value())
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if simulate(state, [(state.request_date, Decimal(mid) * unit)]).ok:
            lo = mid
        else:
            hi = mid - 1
    return quantize_money(Decimal(lo) * unit, state.home)


def earliest_full_date(state) -> date | None:
    """First date the full amount is safe as ONE payment (no changes)."""
    for offset in range(WINDOW_DAYS):
        day = state.request_date + timedelta(days=offset)
        if simulate(state, [(day, state.requested)]).ok:
            return day
    return None
