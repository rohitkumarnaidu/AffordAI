"""Authoritative temporal engine (Checklist Section 14).

Single home for every date semantic in the pipeline::

    request_date      day-0 of the forecast (from requests.csv, never the
                      machine clock)
    event_date        occurred/recorded (history + recurrence detection)
    settlement_date   cash movement (forecast uses THIS, never event_date)
    income_date       settlement of a credit flow
    payment_date      candidate plan cash day
    completion_date   last plan payment day (must be <= deadline)
    forecast_start    == request_date
    forecast_end      == request_date + 89 (90-day window, inclusive)

Rules (locked from docs/specification.md section 7):
- 90-day window is ``[request_date, request_date + 89]`` inclusive.
- A payment exactly ON the deadline day is valid (``<=``, never ``<``).
- Same-day flows share one deterministic order key (never dict/hash order).
- Calendar-aware month arithmetic (Jan 31 -> Feb 28/29 clamp, never +30d).
- Recurrence generators are pure, terminating, duplicate-free.

No system-clock dependency: there is deliberately no call to
``date.today()`` / ``datetime.now()`` anywhere in this module. All dates
flow from the dataset.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

#: 90-day forecast length. forecast_end = start + (WINDOW_DAYS - 1).
WINDOW_DAYS = 90

#: Hard cap on generated occurrences (runaway guard; a 90-day window can
#: never legitimately need more).
_MAX_OCCURRENCES = 500


class TemporalError(Exception):
    """Deterministic temporal failure (malformed metadata, never silent)."""


def normalize_date(value: object, what: str = "date") -> date:
    """Normalize to a ``datetime.date`` (date-only semantics).

    Accepts ``date`` (identity) and ``datetime`` (truncated to its calendar
    day — no timezone conversion is applied). Anything else raises
    :class:`TemporalError` (never falls back to "today").
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TemporalError(f"{what}: expected date, got {value!r}")


def forecast_start(request_date: date) -> date:
    """Day-0 of the forecast (== request_date, validated)."""
    return normalize_date(request_date, "request_date")


def forecast_end(request_date: date) -> date:
    """Last forecast day: request_date + 89 (inclusive 90-day window)."""
    start = normalize_date(request_date, "request_date")
    return start + timedelta(days=WINDOW_DAYS - 1)


def in_window(day: date, request_date: date) -> bool:
    """True iff ``forecast_start <= day <= forecast_end``."""
    day = normalize_date(day, "day")
    start = normalize_date(request_date, "request_date")
    return start <= day <= start + timedelta(days=WINDOW_DAYS - 1)


def is_deadline_day(day: date, deadline: date) -> bool:
    """True iff the payment day is exactly the deadline."""
    return normalize_date(day, "day") == normalize_date(deadline, "deadline")


def meets_deadline(day: date, deadline: date) -> bool:
    """Deadline gate: completion ON the deadline day is valid (``<=``)."""
    return normalize_date(day, "day") <= normalize_date(deadline, "deadline")


def first_future_day(request_date: date) -> date:
    """The calendar day after the request date (window day 2)."""
    return normalize_date(request_date, "request_date") + timedelta(days=1)


def add_days(day: date, n: int) -> date:
    """Calendar-day addition (no month-length assumptions)."""
    return normalize_date(day, "day") + timedelta(days=int(n))


def clamp_month_day(year: int, month: int, dom: int) -> date:
    """Month-aware day construction: ``Feb 30 -> Feb 28/29`` (clamp).

    Raises:
        TemporalError: ``dom`` outside 1..31 or invalid year/month.
    """
    if not 1 <= int(dom) <= 31:
        raise TemporalError(f"invalid day-of-month {dom!r}")
    if not 1 <= int(month) <= 12:
        raise TemporalError(f"invalid month {month!r}")
    last = calendar.monthrange(int(year), int(month))[1]
    return date(int(year), int(month), min(int(dom), last))


def generate_monthly_occurrences(start: date, end: date, dom: int) -> list[date]:
    """Pure monthly schedule within ``[start, end]`` on day-of-month ``dom``.

    Month-length aware (clamped); duplicate-free; terminating. ``end < start``
    yields ``[]`` (recurrence outside the forecast produces nothing — it is
    never an error to have zero occurrences).
    """
    start = normalize_date(start, "start")
    end = normalize_date(end, "end")
    if end < start:
        return []
    dom = int(dom)  # validated inside clamp_month_day
    out: list[date] = []
    # First candidate month: the month containing `start`.
    year, month = start.year, start.month
    guard = 0
    while True:
        day = clamp_month_day(year, month, dom)
        if day > end:
            break
        if day >= start and day not in out:
            out.append(day)
        # advance one calendar month
        month += 1
        if month > 12:
            month = 1
            year += 1
        guard += 1
        if guard > _MAX_OCCURRENCES:
            raise TemporalError("monthly recurrence runaway (guard tripped)")
        if guard > 1200:  # unreachable; keeps linters honest about termination
            break
    return out


def generate_interval_occurrences(
    anchor: date, start: date, end: date, gap_days: int
) -> list[date]:
    """Pure fixed-interval schedule: ``anchor + k*gap`` within ``[start,end]``.

    Raises:
        TemporalError: ``gap_days < 1`` (invalid frequency/interval metadata).
    """
    anchor = normalize_date(anchor, "anchor")
    start = normalize_date(start, "start")
    end = normalize_date(end, "end")
    gap = int(gap_days)
    if gap < 1:
        raise TemporalError(f"invalid recurrence interval {gap_days!r}")
    if end < start:
        return []
    day = anchor
    if day < start:
        skips = (start - day).days // gap + 1
        day = day + timedelta(days=gap * skips)
    out: list[date] = []
    guard = 0
    while day <= end:
        out.append(day)
        day = day + timedelta(days=gap)
        guard += 1
        if guard > _MAX_OCCURRENCES:
            raise TemporalError("interval recurrence runaway (guard tripped)")
    # Invariant: uniqueness required by the contract.
    assert len(set(out)) == len(out), "recurrence produced duplicate dates"
    return out


def flow_sort_key(flow) -> tuple:
    """Deterministic same-day order key (never dict/hash order).

    Primary: day. Secondary: signed home amount (outflows before inflows of
    the same day is stable and reproducible). Tertiary: event/source ids.
    """
    return (
        flow.day,
        flow.amount_home,
        str(getattr(flow, "event_id", "") or ""),
        str(getattr(flow, "source_event_id", "") or ""),
    )


def assert_unique_dates(days: list[date], what: str = "recurrence") -> None:
    """Contract invariant: a recurrence must not produce duplicate dates."""
    if len(set(days)) != len(days):
        raise TemporalError(f"{what}: duplicate occurrence dates {days!r}")
