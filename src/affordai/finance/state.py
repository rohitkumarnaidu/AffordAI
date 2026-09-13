"""Canonical financial state: opening balance, floor, and dated flows."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from affordai.finance.timeline import Flow


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


def build(ctx, flows: list[Flow], unknowns: list[dict], notes: list[str]) -> FinancialState:
    req = ctx.request
    prof = ctx.profile
    state = FinancialState(
        request_id=req["request_id"],
        user_id=req["user_id"],
        request_date=req["request_date"],
        deadline=req["desired_completion_date"],
        home=prof["home_currency"],
        opening=prof["current_available_balance"],
        minimum=prof["minimum_balance_to_keep"],
        requested=req["requested_amount"],
        flows=flows,
        unknowns=unknowns,
        notes=list(notes),
        events_by_id={e["event_id"]: e for e in ctx.events},
    )
    net: dict[date, Decimal] = {}
    for f in flows:
        net[f.day] = net.get(f.day, Decimal("0")) + f.amount_home
    state.daily_net = net
    return state
