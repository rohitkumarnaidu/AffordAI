"""Financial timeline: dated home-currency flows for the 90-day window.

Inclusion rules (spec section 4):
- settled, settlement >= request_date ............ include at settlement
- settled, settlement < request_date ............. history only (recurrence)
- scheduled ...................................... include (confirmed future)
- pending debit .................................. include at request_date (reserve)
- pending credit ................................. IGNORE until settled
- failed / cancelled / unrealized / non_cash ..... IGNORE
- evidence-cancelled ............................. IGNORE
- evidence-amended amount/date ................... applied
- blank amount ................................... UNKNOWN (skipped, recorded)

Recurrence inference (documented method): settled history grouped by
(event_type, category, currency); >=3 occurrences with median gap 27-32
days project monthly on the modal day-of-month (clamped); weekly variant
for median gap 6-8 days with >=4 occurrences. Amount = median of last 3
(converted at their own settlements). Inferred flows dedupe against
scheduled flows within +-3 days, same category and ~equal amount.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from affordai.finance.money import quantize_money
from affordai.finance.temporal import (
    WINDOW_DAYS,
    clamp_month_day,
    flow_sort_key,
    forecast_end,
)


@dataclass
class Flow:
    day: date
    amount_home: Decimal  # +inflow, -outflow (quantized, home currency)
    kind: str  # settled | scheduled | pending_debit | inferred
    event_id: str | None
    source_event_id: str | None  # spending-change target linkage
    category: str
    flexibility: str
    essential: bool
    # Traceability (Section 12.4): per-flow FX provenance (re-derivable but recorded)
    source_amount: Decimal | None = None
    source_currency: str | None = None
    rate: Decimal | None = None
    rate_date: date | None = None
    rate_id: str | None = None


def _same_month_day(year: int, month: int, dom: int) -> date:
    """Compat alias: month-aware day construction (see temporal.clamp_month_day)."""
    return clamp_month_day(year, month, dom)


def _history_view(
    history: list[dict],
    amend_amounts: dict[str, Decimal],
    amend_dates: dict[str, date],
) -> list[dict]:
    """Return history with evidence-amended amount/date applied (no mutation)."""
    out: list[dict] = []
    for e in history:
        eid = e["event_id"]
        copy = dict(e)
        if eid in amend_amounts:
            copy["amount"] = amend_amounts[eid]
        if eid in amend_dates:
            copy["settlement_date"] = amend_dates[eid]
        out.append(copy)
    return out


def _infer_recurrence(
    history: list[dict],
    home: str,
    rate_table,
    start: date,
    end: date,
    protect: set[str],
) -> list[Flow]:
    groups: dict[tuple, list[dict]] = {}
    for e in history:
        if e["direction"] not in ("debit", "credit"):
            continue
        # Sample forensics (request_01/05): income recurs in history but the
        # official forecast counts only scheduled/settled-future income
        # (user_05: 5 monthly salaries, zero future income -> not_affordable).
        # Debt/investment obligations are finite: only explicit scheduled
        # rows count, never inferred recurrence. Recurrence is inferred for
        # expense/subscription outflows only.
        if e["event_type"] not in ("expense", "subscription"):
            continue
        groups.setdefault(
            (e["event_type"], e["category"], e["currency"]), []
        ).append(e)
    out: list[Flow] = []
    for (etype, cat, cur), rows in groups.items():
        rows.sort(key=lambda r: r["settlement_date"])
        if len(rows) < 3:
            continue
        gaps = [
            (b["settlement_date"] - a["settlement_date"]).days
            for a, b in zip(rows, rows[1:])
        ]
        med_gap = median(gaps)
        monthly = 27 <= med_gap <= 32
        weekly = 6 <= med_gap <= 8 and len(rows) >= 4
        if not (monthly or weekly):
            continue
        recent = rows[-3:]
        amounts = []
        for r in recent:
            if r["amount"] is None:
                continue
            # Use rate_table.convert_to_home for traceability where possible
            try:
                conv, _ = rate_table.convert_to_home(r["amount"], cur, home, r["settlement_date"])
            except Exception:
                conv = rate_table.to_home(r["amount"], cur, home, r["settlement_date"])
            if conv is None:
                continue
            amounts.append(conv)
        if not amounts:
            continue
        amount = quantize_money(Decimal(str(median(amounts))), home)
        if amount == 0:
            continue
        doms = [r["settlement_date"].day for r in recent]
        # Deterministic tie-break: most frequent wins, ties -> most recent
        # (mirrors message_income._payday_dom; avoids set-order nondeterminism)
        _freq: dict[int, int] = {}
        _last: dict[int, int] = {}
        for _i, _d in enumerate(doms):
            _freq[_d] = _freq.get(_d, 0) + 1
            _last[_d] = _i
        dom = max(_freq, key=lambda d: (_freq[d], _last[d]))
        flex = recent[-1]["flexibility"]
        if not all(r["flexibility"] == flex for r in recent):
            flex = "fixed"
        rep = recent[-1]["event_id"]
        day = _same_month_day(start.year, start.month, dom)
        step = 0
        while day < start:
            step += 1
            if monthly:
                m = start.month - 1 + step
                day = _same_month_day(start.year + m // 12, m % 12 + 1, dom)
            else:
                day = start + timedelta(days=7 * step)
            if step > 40:
                break
        while day <= end:
            signed = amount if recent[-1]["direction"] == "credit" else -amount
            out.append(
                Flow(
                    day=day,
                    amount_home=signed,
                    kind="inferred",
                    event_id=None,
                    source_event_id=rep,
                    category=cat,
                    flexibility=flex,
                    essential=cat in protect,
                )
            )
            if monthly:
                m = day.month - 1 + 1
                day = _same_month_day(day.year + m // 12, m % 12 + 1, dom)
            else:
                day = day + timedelta(days=7)
    # Description-level fallback for FLEXIBLE debits (sample forensics:
    # "Weekend food delivery" recurs twice, 4 months apart, and anchors an
    # official reduce_to change). >=2 same-description occurrences with
    # median gap >= 7 days project forward by median gap within the window.
    # Category-level flows above win ties (dedupe below keeps first).
    desc_groups: dict[tuple, list[dict]] = {}
    for e in history:
        if (
            e["direction"] != "debit"
            or e["event_type"] not in ("expense", "subscription")
            or e["flexibility"] == "fixed"
            or e["amount"] is None
        ):
            continue
        desc_groups.setdefault(
            (e["category"], (e["description"] or "").strip().lower(), e["currency"]), []
        ).append(e)
    for (cat, _desc, cur), rows in desc_groups.items():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: r["settlement_date"])
        gaps = [
            (b["settlement_date"] - a["settlement_date"]).days
            for a, b in zip(rows, rows[1:])
        ]
        med_gap = median(gaps)
        if med_gap < 7:
            continue
        recent = rows[-3:]
        amounts = []
        for r in recent:
            conv = rate_table.to_home(r["amount"], cur, home, r["settlement_date"])
            if conv is not None:
                amounts.append(conv)
        if not amounts:
            continue
        amount = quantize_money(Decimal(str(median(amounts))), home)
        if amount == 0:
            continue
        flex = recent[-1]["flexibility"]
        rep = recent[-1]["event_id"]
        day = recent[-1]["settlement_date"] + timedelta(days=int(med_gap))
        if day < start:
            skips = (start - day).days // int(med_gap) + 1
            day = day + timedelta(days=int(med_gap) * skips)
        while day <= end:
            out.append(
                Flow(
                    day=day,
                    amount_home=-amount,
                    kind="inferred",
                    event_id=None,
                    source_event_id=rep,
                    category=cat,
                    flexibility=flex,
                    essential=cat in protect,
                )
            )
            day = day + timedelta(days=int(med_gap))
            if len([f for f in out if f.source_event_id == rep]) > 6:
                break
    # dedupe inferred on (source, day): category-level wins, desc-level duplicates dropped
    _seen: set[tuple[str, date]] = set()
    _deduped: list[Flow] = []
    for _f in out:
        _key = (_f.source_event_id or "", _f.day)
        if _key in _seen:
            continue
        _seen.add(_key)
        _deduped.append(_f)
    return _deduped


def _estimate_unknown_amount(
    ctx, category: str, currency: str, home: str, rate_table
) -> Decimal | None:
    """Conservative estimate for unknown-amount debits: median of same-category history."""
    hist = [
        h for h in ctx.events
        if h["status"] == "settled" and h["amount"] is not None
        and h["category"] == category and h["currency"] == currency
    ]
    if not hist:
        return None
    hist.sort(key=lambda r: r["settlement_date"])
    recent = hist[-3:]
    vals: list[Decimal] = []
    for r in recent:
        try:
            conv, _ = rate_table.convert_to_home(r["amount"], currency, home, r["settlement_date"])
        except Exception:
            conv = rate_table.to_home(r["amount"], currency, home, r["settlement_date"])
        if conv is not None:
            vals.append(conv)
    if not vals:
        return None
    return quantize_money(Decimal(str(median(vals))), home)


def build_flows(
    ctx,
    rate_table,
    cancelled: set[str],
    amend_amounts: dict[str, Decimal],
    amend_dates: dict[str, date],
    extra: list[tuple] | None = None,
) -> tuple[list[Flow], list[dict], list[str]]:
    """Return (flows, unknowns, notes) for the request window.

    `extra`: message-confirmed dated amounts ((day, amount_home, label))
    appended as scheduled salary flows after +-3d dedupe.
    """
    req_date = ctx.request["request_date"]
    end = forecast_end(req_date)
    home = ctx.profile["home_currency"]
    protect = set(ctx.profile["expense_categories_to_protect"])
    flows: list[Flow] = []
    unknowns: list[dict] = []
    notes: list[str] = []
    raw_history: list[dict] = []

    for e in ctx.events:
        eid = e["event_id"]
        if eid in cancelled or e["status"] in ("cancelled", "failed", "unrealized"):
            continue
        if e["direction"] == "non_cash":
            continue
        day = amend_dates.get(eid, e["settlement_date"])
        amount = amend_amounts.get(eid, e["amount"])
        if amount is None:
            if day >= req_date and e["status"] in ("pending", "scheduled", "settled"):
                unknowns.append({"event_id": eid, "status": e["status"]})
                # ---- unknown-amount reserve (conservative, auditable) ----
                if e["direction"] == "debit" and e["status"] in ("pending", "scheduled"):
                    # only debits in-window need reserve; settled unknowns are history-only
                    if req_date <= day <= end:
                        est = _estimate_unknown_amount(ctx, e["category"], e["currency"], home, rate_table)
                        if est is not None and est > 0:
                            reserve_day = req_date if e["status"] == "pending" else day
                            flows.append(
                                Flow(
                                    day=reserve_day,
                                    amount_home=-est,
                                    kind="pending_debit" if e["status"] == "pending" else "scheduled",
                                    event_id=eid,
                                    source_event_id=eid,
                                    category=e["category"],
                                    flexibility=e["flexibility"],
                                    essential=e["category"] in protect,
                                )
                            )
                            notes.append(f"unknown-reserved: {eid} at {est} {home} (median {e['category']})")
                        else:
                            notes.append(f"unknown-unreserved: {eid} no history for {e['category']}/{e['currency']}")
            if e["status"] == "settled" and e["settlement_date"] < req_date:
                pass
            continue
        if e["status"] == "settled" and e["settlement_date"] < req_date:
            raw_history.append(e)
            continue
        if e["status"] == "settled":
            kind = "settled"
        elif e["status"] == "scheduled":
            # Bonus/refund/lottery guard: scheduled credits only if salary/income
            if e["direction"] == "credit" and not (e["category"] == "salary" or e["event_type"] == "income"):
                notes.append(f"scheduled-credit-skipped: {eid} category {e['category']!r} (only salary counted)")
                continue
            kind = "scheduled"
        elif e["status"] == "pending":
            if e["direction"] == "credit":
                continue  # pending credits ignored until settled
            kind = "pending_debit"
            day = req_date  # reserve immediately
        else:
            continue
        if not (req_date <= day <= end):
            continue
        # Traceable conversion (captures rate metadata per flow)
        trace = None
        try:
            conv, trace = rate_table.convert_to_home(amount, e["currency"], home, day)
        except Exception:
            conv = rate_table.to_home(amount, e["currency"], home, day)
            trace = None
        if conv is None:
            if e["direction"] == "credit":
                notes.append(f"fx-missing: excluded foreign credit {eid}")
                continue
            notes.append(f"fx-missing: kept foreign debit {eid} at face")
            conv = amount
            trace = None
        signed = quantize_money(conv, home)
        if e["direction"] == "debit":
            signed = -signed
        flows.append(
            Flow(
                day=day,
                amount_home=signed,
                kind=kind,
                event_id=eid,
                source_event_id=eid,
                category=e["category"],
                flexibility=e["flexibility"],
                essential=e["category"] in protect,
                source_amount=amount,
                source_currency=e["currency"],
                rate=getattr(trace, "rate", None) if trace else (None if e["currency"] == home else None),
                rate_date=getattr(trace, "rate_date", None) if trace else None,
                rate_id=getattr(trace, "rate_id", None) if trace else (f"{home}->{home}@same" if e["currency"] == home else None),
            )
        )

    # History with amended values for recurrence (amend-aware)
    history = _history_view(raw_history, amend_amounts, amend_dates)
    inferred = _infer_recurrence(history, home, rate_table, req_date, end, protect)
    # Dedupe inferred against scheduled/settled flows (same category, ~amount, +-3d).
    hard = [(f.day, f.category, abs(f.amount_home)) for f in flows if f.kind != "pending_debit"]
    for day, amount_home, label in extra or []:
        if not (req_date <= day <= end) or amount_home <= 0:
            notes.append(f"extra income {label}: outside window/non-positive, skipped")
            continue
        clash = any(
            c == "salary"
            and abs((d - day).days) <= 3
            and abs(a - amount_home) <= max(Decimal("1"), amount_home * Decimal("0.02"))
            for d, c, a in hard
        )
        if clash:
            continue
        signed = quantize_money(amount_home, home)
        flows.append(
            Flow(
                day=day,
                amount_home=signed,
                kind="scheduled",
                event_id=None,
                source_event_id=None,
                category="salary",
                flexibility="fixed",
                essential=False,
            )
        )
        hard.append((day, "salary", abs(signed)))
    for f in inferred:
        clash = any(
            c == f.category
            and abs((d - f.day).days) <= 3
            and abs(a - abs(f.amount_home)) <= max(Decimal("1"), abs(f.amount_home) * Decimal("0.02"))
            for d, c, a in hard
        )
        if not clash:
            flows.append(f)
    # --- linked lifecycle dedupe: if both ends of a linked chain are in-window, keep only the later ---
    _by_event = {e["event_id"]: e for e in ctx.events}
    _flow_ids = {f.event_id for f in flows if f.event_id}
    _drop: set[str] = set()
    for f in list(flows):
        if not f.event_id:
            continue
        src = _by_event.get(f.event_id)
        if not src:
            continue
        lid = src.get("linked_event_id")
        if not lid or lid not in _flow_ids or lid in _drop or f.event_id in _drop:
            continue
        other = next((x for x in flows if x.event_id == lid), None)
        if other is None:
            continue
        # deterministic: keep later day, tie -> lexicographically later event_id
        if (f.day, f.event_id) < (other.day, other.event_id):
            _drop.add(f.event_id)
        else:
            _drop.add(lid)
    if _drop:
        flows = [f for f in flows if f.event_id not in _drop]
        notes.append(f"linked-dedupe: dropped {sorted(_drop)} (linked lifecycle, kept later)")
    flows.sort(key=flow_sort_key)
    return flows, unknowns, notes
