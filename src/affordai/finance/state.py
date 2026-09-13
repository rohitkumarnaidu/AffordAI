"""Canonical financial state (Checklist Section 13).

One normalized ``FinancialState`` per request, built as::

    raw input -> temporal normalization -> currency normalization
    -> canonical financial state -> 90-day forecast

The forecast engine receives THIS object — it never reconstructs state
from raw CSVs, so no two modules can compute different financial
realities. Raw records are never mutated: ``build()`` copies what it
needs and preserves ``original_index``/ids/provenance.

Treatment summary (see docs/specification.md section 4; flow inclusion
is decided in ``timeline.build_flows`` and only *validated* here):
- opening balance / minimum floor: authoritative profile values.
- confirmed salary: counted only on its settlement date.
- pending debits: reserved (present in flows at request_date).
- pending credits / bonuses / refunds / lottery / unrealized gains:
  excluded until settled (absent from flows).
- failed / cancelled / unrealized / non-cash / duplicate flows: absent.
- unrealized investment value: never spendable cash (absent).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from affordai.finance.currency import SUPPORTED_CURRENCIES, normalize_currency
from affordai.finance.temporal import TemporalError, forecast_end, normalize_date
from affordai.finance.timeline import Flow

#: Flexibility categories (Tier-1 contract; closed set).
FLEXIBILITIES = frozenset({"fixed", "reducible", "stoppable", "reducible_or_stoppable"})

#: Flex values that permit a stop / a reduction (single source of truth;
#: spending_changes.py imports these — no duplicate definitions).
STOP_OK = frozenset({"stoppable", "reducible_or_stoppable"})
REDUCE_OK = frozenset({"reducible", "reducible_or_stoppable"})


class StateError(Exception):
    """Deterministic financial-state failure (invalid input, never silent)."""


def _require_money(value: object, what: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise StateError(f"{what}: expected Decimal, got {value!r}")
    if not value.is_finite():
        raise StateError(f"{what}: non-finite amount {value!r}")
    return value


def is_protected(category: str, profile: dict) -> bool:
    """True iff the category is in the user's protected list."""
    return str(category) in set(profile.get("expense_categories_to_protect", []))


def stop_allowed(row: dict, profile: dict) -> tuple[bool, str]:
    """Whether a stop change on this event row is permitted.

    Returns ``(ok, reason)``. Protected categories and non-stoppable
    flexibility reject deterministically.
    """
    flex = str(row.get("flexibility", ""))
    cat = str(row.get("category", ""))
    if flex not in FLEXIBILITIES:
        return False, f"unknown flexibility {flex!r}"
    if cat in set(profile.get("expense_categories_to_protect", [])):
        return False, f"protected category {cat!r}"
    if flex not in STOP_OK:
        return False, f"flexibility {flex!r} is not stoppable"
    if cat not in set(profile.get("willing_to_stop", [])):
        return False, f"user not willing to stop {cat!r}"
    return True, "stop permitted"


def validate_reduction(row: dict, profile: dict, new_amount: object) -> Decimal:
    """Validate a reduce_to target. Returns the normalized Decimal.

    Rules: reducible flexibility + willing category + not protected +
    ``new_amount >= minimum_allowed_amount`` (exact minimum is valid;
    below-minimum / zero-for-nonzero-minimum / negative reject).

    Raises:
        StateError: any rule violated (invalid reductions never apply).

    Policy note: a blank/``None`` ``minimum_allowed_amount`` fails the
    ``Decimal`` type gate, so no ``reduce_to`` is offered on that event
    (only ``stop``, if otherwise eligible). This is the conservative
    reading — never invent a reduction floor the dataset did not state.
    """
    flex = str(row.get("flexibility", ""))
    cat = str(row.get("category", ""))
    if flex not in FLEXIBILITIES:
        raise StateError(f"unknown flexibility {flex!r}")
    if cat in set(profile.get("expense_categories_to_protect", [])):
        raise StateError(f"protected category {cat!r} cannot be reduced")
    if flex not in REDUCE_OK:
        raise StateError(f"flexibility {flex!r} is not reducible")
    if cat not in set(profile.get("willing_to_reduce", [])):
        raise StateError(f"user not willing to reduce {cat!r}")
    if not isinstance(new_amount, Decimal):
        raise StateError(f"new_amount must be Decimal, got {new_amount!r}")
    if not new_amount.is_finite():
        raise StateError(f"new_amount non-finite {new_amount!r}")
    if new_amount < 0:
        raise StateError(f"new_amount negative {new_amount!r}")
    floor = row.get("minimum_allowed_amount")
    if floor is not None:
        if not isinstance(floor, Decimal):
            raise StateError(f"minimum_allowed_amount must be Decimal, got {floor!r}")
        if new_amount < floor:
            raise StateError(
                f"new_amount {new_amount} below minimum_allowed_amount {floor}"
            )
    return new_amount


@dataclass
class FinancialState:
    request_id: str
    user_id: str
    request_date: date
    deadline: date
    home: str
    opening: Decimal
    minimum: Decimal
    requested: Decimal
    flows: list[Flow] = field(default_factory=list)
    unknowns: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    events_by_id: dict = field(default_factory=dict)
    # Precomputed base daily net (inflows positive) for the window.
    daily_net: dict = field(default_factory=dict)
    # Provenance: source record ids for this state (never secrets).
    provenance: dict = field(default_factory=dict)


def build(ctx, flows: list[Flow], unknowns: list[dict], notes: list[str] | None = None) -> FinancialState:
    """Build + validate the canonical state (raises StateError, never silent)."""
    req = ctx.request
    prof = ctx.profile
    request_id = req.get("request_id")
    user_id = req.get("user_id")
    if not request_id or not user_id:
        raise StateError("request/user identity missing")
    try:
        request_date = normalize_date(req.get("request_date"), "request_date")
    except TemporalError as exc:
        raise StateError(str(exc))
    try:
        deadline = normalize_date(req.get("desired_completion_date"), "deadline")
    except TemporalError as exc:
        raise StateError(str(exc))
    try:
        home = normalize_currency(prof.get("home_currency"))
    except Exception as exc:
        raise StateError(f"home currency: {exc}")
    if home not in SUPPORTED_CURRENCIES:
        raise StateError(f"unsupported home currency {home!r}")
    opening = _require_money(prof.get("current_available_balance"), "opening balance")
    minimum = _require_money(prof.get("minimum_balance_to_keep"), "minimum balance")
    requested = _require_money(req.get("requested_amount"), "requested amount")
    if opening < 0:
        raise StateError(f"opening balance negative {opening}")
    if minimum < 0:
        raise StateError(f"minimum balance negative {minimum}")
    if requested <= 0:
        raise StateError(f"requested amount non-positive {requested}")

    # Normalization gate: every flow must already be home-currency Decimal
    # on a real date inside the window (timeline guarantees this; states
    # built by hand in tests use empty flows and pass trivially).
    end = forecast_end(request_date)
    seen_economic: set[tuple] = set()
    for f in flows:
        if not isinstance(f.day, date):
            raise StateError(f"flow day must be date, got {f.day!r}")
        if not (request_date <= f.day <= end):
            raise StateError(
                f"flow {f.event_id} day {f.day} outside "
                f"[{request_date}, {end}]"
            )
        _require_money(f.amount_home, f"flow {f.event_id} amount")
        # Economic-event double-count guard: the same settled/scheduled event
        # id must appear at most once (inferred flows carry event_id None).
        if f.kind in ("settled", "scheduled", "pending_debit") and f.event_id:
            key = (f.kind, f.event_id, f.day)
            if key in seen_economic:
                raise StateError(f"duplicate economic event counted twice: {key}")
            seen_economic.add(key)

    state = FinancialState(
        request_id=request_id,
        user_id=user_id,
        request_date=request_date,
        deadline=deadline,
        home=home,
        opening=opening,
        minimum=minimum,
        requested=requested,
        flows=list(flows),
        unknowns=list(unknowns or []),
        notes=list(notes or [] if notes is not None else []),
        events_by_id={e["event_id"]: dict(e) for e in ctx.events},
        provenance={
            "request_id": request_id,
            "user_id": user_id,
            "original_index": ctx.request.get("original_index"),
            "n_events": len(ctx.events),
            "n_flows": len(flows),
            "home_currency": home,
        },
    )
    net: dict[date, Decimal] = {}
    for f in flows:
        net[f.day] = net.get(f.day, Decimal("0")) + f.amount_home
    state.daily_net = net
    return state
