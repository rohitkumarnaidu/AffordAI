"""Sections 43-52 zero-trust audit regressions (Sec 44 red-flag fixes).

Each test pins a concrete auditor finding to a failing-input sketch:

- 3B: ISO-date year fragments (2025 in 2025-08-23) must not mint amounts.
- 3A: request-level salary linkage fires ONLY for payroll reporters
  (employer/bank) with confirm semantics and no denial.
- 3C: negated state-changing keywords ("do not cancel") must not emit facts.
- F2: reduce caps are HOME-currency (converted floor); cross-currency
  floors must never compare raw against amount_home flows.

Residual (documented, not fixed in text): location/identifier numbers
("Charge Point 1110") remain ambiguous to a deterministic extractor; the
defense is the image path + conservative UNKNOWN handling, and unlinked
facts are structurally inert (conflict_resolver requires event_id).
"""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

sys.path.insert(0, "src")

from affordai.evidence.message_interpreter import interpret
from affordai.finance.currency import RateTable
from affordai.finance.spending_changes import candidate_targets
from affordai.finance.timeline import Flow
from affordai.pipeline import _link_salary_fact


def _msg(text, source_type="employer", related_event_id=None, mid="m1"):
    return {
        "message_id": mid,
        "request_id": "r1",
        "user_id": "u1",
        "related_event_id": related_event_id,
        "source_type": source_type,
        "sent_at": "2026-09-03T01:00:00Z",
        "message_text": text,
    }


def _kinds(facts):
    return {f.kind for f in facts}


# ---- 3B: year fragments ----------------------------------------------------

def test_year_fragment_of_iso_date_is_not_an_amount():
    facts = interpret(_msg("Your confirmed salary is now expected on 2025-08-23."))
    assert "amend_amount" not in _kinds(facts)


def test_legit_amount_still_extracted():
    facts = interpret(_msg("Your salary pay 59000 confirmed"))
    amends = [f for f in facts if f.kind == "amend_amount"]
    assert len(amends) == 1 and amends[0].normalized_value == "59000"


def test_stated_total_before_a_date_is_kept():
    facts = interpret(_msg("Total 393.22 paid on 2026-09-03 for the session"))
    amends = [f for f in facts if f.kind == "amend_amount"]
    assert len(amends) == 1 and amends[0].normalized_value == "393.22"


# ---- 3A: salary-link gates --------------------------------------------------

def _salary_ctx():
    return SimpleNamespace(
        request={"request_date": date(2026, 9, 4)},
        events=[
            {
                "event_id": "e-sal",
                "status": "scheduled",
                "event_type": "income",
                "category": "salary",
                "settlement_date": date(2026, 9, 15),
            }
        ],
    )


def test_salary_link_rejects_non_payroll_source():
    ctx = _salary_ctx()
    (fact,) = [f for f in interpret(_msg("salary correction pay 9000000", source_type="merchant")) if f.kind == "amend_amount"]
    assert fact.event_id is None
    _link_salary_fact(ctx, _msg("salary correction pay 9000000", source_type="merchant"), fact)
    assert fact.event_id is None


def test_salary_link_accepts_employer_confirm():
    ctx = _salary_ctx()
    text = "Your salary pay 59000 confirmed"
    (fact,) = [f for f in interpret(_msg(text, source_type="employer")) if f.kind == "amend_amount"]
    _link_salary_fact(ctx, _msg(text, source_type="employer"), fact)
    assert fact.event_id == "e-sal"


def test_salary_link_vetoes_denial():
    ctx = _salary_ctx()
    text = "Your salary pay 59000 confirmed, but the bonus is still pending"
    (fact,) = [f for f in interpret(_msg(text, source_type="employer")) if f.kind == "amend_amount"]
    _link_salary_fact(ctx, _msg(text, source_type="employer"), fact)
    assert fact.event_id is None


def test_salary_link_requires_confirm_semantics():
    ctx = _salary_ctx()
    text = "salary information pay 59000 for your records"
    cands = [f for f in interpret(_msg(text, source_type="employer")) if f.kind == "amend_amount"]
    assert len(cands) == 1
    _link_salary_fact(ctx, _msg(text, source_type="employer"), cands[0])
    assert cands[0].event_id is None


# ---- 3C: negation guard -----------------------------------------------------

def test_negated_cancel_suppressed():
    facts = interpret(_msg("please do not cancel my standing order", related_event_id="e1"))
    assert "cancel" not in _kinds(facts)


def test_real_cancel_still_fires():
    facts = interpret(
        _msg("Your order has been cancelled and the refund was issued", related_event_id="e1")
    )
    assert "cancel" in _kinds(facts)


def test_negated_delay_suppressed():
    facts = interpret(
        _msg("Your payment was not delayed and arrived on time", related_event_id="e1")
    )
    assert "delay" not in _kinds(facts)


def test_real_delay_still_fires():
    facts = interpret(
        _msg("Your payment was delayed by two days", related_event_id="e1")
    )
    assert "delay" in _kinds(facts)


# ---- F2: home-currency reduce caps ------------------------------------------

def _fx_state():
    d = date(2026, 9, 3)
    row = {
        "event_id": "e1",
        "event_type": "subscription",
        "category": "streaming",
        "flexibility": "reducible",
        "minimum_allowed_amount": Decimal("100"),  # 100 USD (source units)
        "currency": "USD",
        "settlement_date": d,
    }
    flows = [
        Flow(day=date(2026, 9, 5), amount_home=Decimal("-9000"), kind="scheduled",
             event_id="e1", source_event_id="e1", category="streaming",
             flexibility="reducible", essential=False),
        Flow(day=date(2026, 10, 5), amount_home=Decimal("-9000"), kind="scheduled",
             event_id="e1", source_event_id="e1", category="streaming",
             flexibility="reducible", essential=False),
    ]
    state = SimpleNamespace(home="INR", flows=flows, events_by_id={"e1": row})
    profile = {
        "expense_categories_to_protect": [],
        "willing_to_reduce": ["streaming"],
        "willing_to_stop": [],
    }
    rates = RateTable(
        [{"rate_date": d, "from_currency": "USD", "to_currency": "INR", "rate": Decimal("80")}]
    )
    return state, profile, rates


def test_cross_currency_reduce_cap_is_converted():
    state, profile, rates = _fx_state()
    targets = [t for t in candidate_targets(state, profile, rates)
               if t.event_id == "e1" and t.mode == "reduce"]
    assert len(targets) == 1
    # 100 USD @ 80 = 8000 INR home cap -- NEVER the raw 100 (old phantom).
    assert targets[0].new_amount == Decimal("8000")
    assert targets[0].new_amount != Decimal("100")
    assert targets[0].saving == Decimal("2000")


def test_cross_currency_reduce_without_rates_is_skipped():
    state, profile, _ = _fx_state()
    targets = [t for t in candidate_targets(state, profile)
               if t.event_id == "e1" and t.mode == "reduce"]
    assert targets == []


def test_same_currency_reduce_unchanged_without_rates():
    state, profile, _ = _fx_state()
    state.home = "USD"
    state.flows[0].amount_home = Decimal("-900")
    state.flows[1].amount_home = Decimal("-900")
    state.events_by_id["e1"]["currency"] = "USD"
    targets = [t for t in candidate_targets(state, profile)
               if t.event_id == "e1" and t.mode == "reduce"]
    assert len(targets) == 1
    assert targets[0].new_amount == Decimal("100")
