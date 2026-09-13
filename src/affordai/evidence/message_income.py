"""Message-confirmed salary income (narrow deterministic E1).

Why this exists: several sample users have monthly salary history but NO
scheduled income rows, yet employer messages confirm upcoming pay
(e.g. raise生效, resume, next-payroll confirmation) and the expected
decisions treat that pay as real. Without it, affordable rows collapse.

Strict bounds (anti-overfit):
- Only `employer` source messages with confirm/raise/resume semantics AND
  salary keywords. Denials ("still pending", "not approved", "until ...
  completed") NEVER create income (regression-tested).
- Amount: explicitly stated preferred; else routine = median of the last 3
  settled salary settlements (documented heuristic, confidence < 1).
- Explicit non-home currency code -> skip with note (never convert blindly).
- Timing: ongoing markers (rais*, resume*, monthly, bulanan, berlaku mulai,
  temporary ... continues) -> monthly series on historical payday;
  otherwise ONE next-payday occurrence ("next payroll", "first salary").
- Payday: modal day-of-month of last-3 settled salary settlements, else the
  effective/explicit date's day. Series bounded by the 90-day window.
- Dedupe: skips dates within +-3 days of an existing scheduled salary flow.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

CONFIRM_RE = re.compile(
    r"confirm(?:ed|ation)?|konfirmasi|updated|update|pembaruan|resumes?|"
    r"raise[sd]?|naik|berlaku mulai|will be|expected on|replaces|revised|"
    r"continues?|scheduled|latest payroll",
    re.I,
)
DENY_RE = re.compile(
    r"still pending|not approved|belum disetujui|belum|menunggu|tidak masuk|"
    r"until .* complet|can change|isn.t withdrawable|has not|have not|"
    r"not been credited|not.*credited|no .* proceeds|no cash",
    re.I,
)
ONGOING_RE = re.compile(
    r"rais|resume|monthly|bulanan|berlaku mulai|temporary|resumes",
    re.I,
)
ONEOFF_RE = re.compile(r"first salary|next payroll|berikutnya", re.I)
CUR_RE = re.compile(r"(EUR|USD|IDR|INR|ZAR|Rp|\$|€)")

from affordai.evidence.message_interpreter import _AMOUNT_RE, _DATE_RE, SALARY_RE


def _routine_amount(ctx) -> Decimal | None:
    rows = sorted(
        (
            e
            for e in ctx.events
            if e["status"] == "settled"
            and (e["event_type"] == "income" or e["category"] == "salary")
            and e["amount"] is not None
        ),
        key=lambda e: e["settlement_date"],
    )[-3:]
    if not rows:
        return None
    return Decimal(str(median([r["amount"] for r in rows])))


def _payday_dom(ctx, fallback: int) -> int:
    rows = sorted(
        (
            e
            for e in ctx.events
            if e["status"] == "settled"
            and (e["event_type"] == "income" or e["category"] == "salary")
        ),
        key=lambda e: e["settlement_date"],
    )[-6:]
    if not rows:
        return fallback
    # Most frequent day-of-month; ties -> most recent (routine payday beats
    # one-off extras like mid-month commissions/adjustments).
    freq: dict[int, int] = {}
    last_seen: dict[int, int] = {}
    for i, r in enumerate(rows):
        freq[r["settlement_date"].day] = freq.get(r["settlement_date"].day, 0) + 1
        last_seen[r["settlement_date"].day] = i
    return max(freq, key=lambda d: (freq[d], last_seen[d]))


def confirmed_series(ctx, message: dict, home: str):
    """Return (incomes, notes); incomes = list of (day, amount_home)."""
    notes: list[str] = []
    if message.get("source_type") != "employer":
        return [], notes
    text = message.get("message_text") or ""
    if not SALARY_RE.search(text):
        return [], notes
    m = _AMOUNT_RE.search(text)
    stated = None
    if m:
        try:
            stated = Decimal(m.group(1).replace(",", ""))
        except Exception:
            stated = None
    if not CONFIRM_RE.search(text):
        return [], notes
    if stated is None and DENY_RE.search(text):
        # Denial with no confirmed amount (unapproved bonus/commission/
        # pending payout): create nothing. A STATED confirmed amount still
        # proceeds (the denial targets the unstated part, e.g. commission).
        notes.append(f"{message['message_id']}: payroll denial, no income created")
        return [], notes

    amount = None
    explicitly_stated = False
    if stated is not None:
        amount = stated
        explicitly_stated = True
    cur = CUR_RE.search(text)
    if cur:
        code = {"Rp": "IDR", "$": None, "€": None}.get(cur.group(1), cur.group(1))
        if code is not None and code != home:
            notes.append(f"{message['message_id']}: non-home pay currency, skipped")
            return [], notes
    if amount is None:
        amount = _routine_amount(ctx)
        if amount is None:
            notes.append(f"{message['message_id']}: no routine amount, skipped")
            return [], notes

    dates = _DATE_RE.findall(text)
    req_date = ctx.request["request_date"]
    from affordai.finance.temporal import forecast_end as _forecast_end

    end = _forecast_end(req_date)
    ongoing = bool(ONGOING_RE.search(text)) and not (
        bool(ONEOFF_RE.search(text)) and not bool(re.search(r"rais|resume|temporary|monthly|bulanan", text, re.I))
    )
    if dates:
        from datetime import datetime as _dt

        anchor = _dt.strptime(dates[0], "%Y-%m-%d").date()
    else:
        anchor = req_date
    dom = _payday_dom(ctx, anchor.day)

    if not ongoing:
        day = _next_payday(req_date, dom, anchor if dates else None)
        if day is None or not (req_date <= day <= end):
            notes.append(f"{message['message_id']}: one-off pay outside window")
            return [], notes
        return [(day, amount)], notes

    series = []
    day = _next_payday(req_date, dom, anchor if dates and ("berlaku" in text or "mulai" in text or "effective" in text.lower() or "resumes" in text.lower()) else None)
    from affordai.finance.temporal import clamp_month_day as _clamp

    while day is not None and day <= end:
        series.append((day, amount))
        mth = day.month + 1
        y = day.year + (mth - 1) // 12
        m = (mth - 1) % 12 + 1
        day = _clamp(y, m, dom)
        if len(series) > 4:
            break
    return series, notes


def _next_payday(req_date: date, dom: int, earliest: date | None) -> date | None:
    from affordai.finance.temporal import clamp_month_day as _clamp

    for step in range(5):
        m = req_date.month - 1 + step
        y = req_date.year + m // 12
        day = _clamp(y, m % 12 + 1, dom)
        if day >= req_date and (earliest is None or day >= earliest):
            return day
    return None
