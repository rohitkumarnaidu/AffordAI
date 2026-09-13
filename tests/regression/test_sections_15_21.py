"""Sections 15-21 gap coverage: safe/earliest/plans/spending/eligibility/optimizer.

Only asserts MISSING properties (audited 2026-09-13): existing suites already
cover floor-exact boundary, zero-amount, deadline-day, window-end, spending
flip, chain e2e, ranking rules 1-3 and installment term. Every state here is
synthetic and dynamic — no hardcoded output.csv values.
"""
import inspect
import sys
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, "src")

from affordai.decision import rules as decision_rules
from affordai.decision.eligibility import filter_candidates
from affordai.finance import optimizer, payment_plans, spending_changes
from affordai.finance.forecast import earliest_full_date, max_safe_today, simulate
from affordai.finance.payment_plans import Candidate
from affordai.finance.state import FinancialState
from affordai.finance.timeline import Flow
from affordai.ingestion.payment_options import expand_schedule


def _state(**kw):
    args = dict(
        request_id="r-gap",
        user_id="u-gap",
        request_date=date(2025, 1, 10),
        deadline=date(2025, 3, 10),
        home="INR",
        opening=Decimal("3000"),
        minimum=Decimal("1000"),
        requested=Decimal("5000"),
        flows=[],
        unknowns=[],
        notes=[],
        events_by_id={},
        daily_net={date(2025, 1, 20): Decimal("4000")},
    )
    args.update(kw)
    return FinancialState(**args)


# ---- Section 16: amount safe to pay ----

def test_safe_plus_unit_rejected_and_bounded():
    st = _state()
    safe = max_safe_today(st)
    assert Decimal("0") <= safe <= st.requested
    assert 0 < safe < st.requested
    assert simulate(st, [(st.request_date, safe)]).ok
    assert not simulate(st, [(st.request_date, safe + Decimal("0.01"))]).ok


def test_safe_monotone_all_below_safe():
    st = _state()
    safe = max_safe_today(st)
    assert simulate(st, [(st.request_date, Decimal("0"))]).ok
    assert simulate(st, [(st.request_date, safe / 2)]).ok
    assert simulate(st, [(st.request_date, safe)]).ok


def test_safe_non_2dp_requested_never_exceeds():
    st = _state(requested=Decimal("100.005"), opening=Decimal("10000"), minimum=Decimal("100"))
    safe = max_safe_today(st)
    assert safe <= st.requested
    assert Decimal("0") <= safe <= st.requested


# ---- Section 17: earliest full-payment date ----

def test_earliest_never_safe_is_none():
    st = _state(opening=Decimal("1000"), minimum=Decimal("1000"),
               requested=Decimal("500"), daily_net={})
    assert max_safe_today(st) == Decimal("0")
    assert earliest_full_date(st) is None


def test_earliest_minimal_every_earlier_day_unsafe():
    st = _state()
    earliest = earliest_full_date(st)
    assert earliest is not None and earliest > st.request_date
    day = st.request_date
    while day < earliest:
        assert not simulate(st, [(day, st.requested)]).ok
        day += timedelta(days=1)
    assert simulate(st, [(earliest, st.requested)]).ok


def test_earliest_independent_of_preferences():
    params = list(inspect.signature(earliest_full_date).parameters)
    assert params == ["state"]  # no profile/method input by construction


# ---- Section 18: payment-plan generator ----

def test_partial_exact_two_payment_shape():
    st = _state()
    safe = max_safe_today(st)
    earliest = earliest_full_date(st)
    assert earliest is not None and earliest <= st.deadline
    cands, _ = payment_plans.generate(st, [], safe, earliest, True)
    partials = [c for c in cands if c.kind == "partial"]
    assert len(partials) == 1
    legs = partials[0].payments
    assert len(legs) == 2
    assert legs[0] == (st.request_date, safe)
    assert legs[1] == (earliest, st.requested - safe)
    assert sum(a for _, a in legs) == st.requested
    assert simulate(st, legs).ok


def test_partial_gated_off():
    st = _state()
    safe = max_safe_today(st)
    earliest = earliest_full_date(st)
    cands, _ = payment_plans.generate(st, [], safe, earliest, False)
    assert [c for c in cands if c.kind == "partial"] == []
    cands2, _ = payment_plans.generate(st, [], safe, None, True)
    assert [c for c in cands2 if c.kind == "partial"] == []
    late = _state(deadline=date(2025, 1, 15))
    late_early = earliest_full_date(late)
    assert late_early is not None and late_early > late.deadline
    cands3, _ = payment_plans.generate(late, [], max_safe_today(late), late_early, True)
    assert [c for c in cands3 if c.kind == "partial"] == []


def _option(**kw):
    opt = dict(
        payment_option_id="opt_7",
        request_id="r-gap",
        payment_method="installments",
        payment_amount=Decimal("1000"),
        number_of_payments=3,
        first_payment_date=date(2025, 1, 10),
        payment_frequency_days=30,
        financing_fee=Decimal("200"),
        total_payable_amount=Decimal("3200"),
    )
    opt.update(kw)
    return opt


def test_installments_exact_option_match():
    st = _state()
    opt = _option()
    cands, notes = payment_plans.generate(
        st, [opt], max_safe_today(st), earliest_full_date(st), True)
    inst = [c for c in cands if c.kind == "installments"]
    assert len(inst) == 1
    assert inst[0].payments == expand_schedule(opt)
    assert inst[0].option_id == "opt_7"
    assert inst[0].total_paid == Decimal("3200")
    assert len(inst[0].payments) == 3
    assert not notes


def test_installments_malformed_skipped_with_note():
    st = _state()
    bad = _option(payment_option_id="opt_bad", payment_frequency_days=None,
                  number_of_payments=3)
    cands, notes = payment_plans.generate(
        st, [bad], max_safe_today(st), earliest_full_date(st), True)
    assert [c for c in cands if c.kind == "installments"] == []
    assert any("opt_bad" in n for n in notes)


def test_wait_shape_conditions():
    st = _state()
    safe = max_safe_today(st)
    earliest = earliest_full_date(st)
    cands, _ = payment_plans.generate(st, [], safe, earliest, True)
    waits = [c for c in cands if c.kind == "wait"]
    assert len(waits) == 1
    assert waits[0].payments == [(earliest, st.requested)]
    rich = _state(daily_net={}, requested=Decimal("1500"))  # safe today -> no wait
    cands2, _ = payment_plans.generate(
        rich, [], max_safe_today(rich), earliest_full_date(rich), True)
    assert [c for c in cands2 if c.kind == "wait"] == []
    cands3, _ = payment_plans.generate(st, [], safe, None, True)
    assert [c for c in cands3 if c.kind == "wait"] == []


# ---- Section 19: spending changes ----

def test_no_gratuitous_changes_for_safe_base():
    st = _state(daily_net={}, requested=Decimal("1500"))  # full today is safe
    base = Candidate("full", [(st.request_date, st.requested)], total_paid=st.requested)
    assert simulate(st, base.payments, {}).ok
    assert spending_changes.find_variants(st, [base], spending_changes.candidate_targets(
        st, {"willing_to_reduce": [], "willing_to_stop": []})) == []


def test_same_event_stop_reduce_exclusive():
    stop = spending_changes.Target("e1", "stop", None, Decimal("100"))
    reduce = spending_changes.Target("e1", "reduce", Decimal("10"), Decimal("40"))
    assert spending_changes._as_changes((stop, reduce)) is None


def test_multi_change_cap_never_exceeds_three():
    req = date(2025, 1, 10)
    flows = [
        Flow(date(2025, 1, 12), Decimal("-4000"), "inferred", None, "e9", "streaming", "stoppable", False),
        Flow(date(2025, 2, 12), Decimal("-4000"), "inferred", None, "e9", "streaming", "stoppable", False),
        Flow(date(2025, 1, 15), Decimal("-3000"), "inferred", None, "e10", "music", "stoppable", False),
        Flow(date(2025, 2, 15), Decimal("-3000"), "inferred", None, "e10", "music", "stoppable", False),
    ]
    net = {}
    for f in flows:
        net[f.day] = net.get(f.day, Decimal("0")) + f.amount_home
    st = FinancialState(
        request_id="r-gap", user_id="u-gap", request_date=req,
        deadline=date(2025, 3, 10), home="INR", opening=Decimal("12000"),
        minimum=Decimal("5000"), requested=Decimal("6000"), flows=flows,
        unknowns=[], notes=[],
        events_by_id={
            "e9": {"event_id": "e9", "flexibility": "stoppable", "category": "streaming",
                   "event_type": "subscription", "minimum_allowed_amount": None},
            "e10": {"event_id": "e10", "flexibility": "stoppable", "category": "music",
                    "event_type": "subscription", "minimum_allowed_amount": None},
        },
        daily_net=net,
    )
    profile = {"willing_to_reduce": [], "willing_to_stop": ["streaming", "music"]}
    targets = spending_changes.candidate_targets(st, profile)
    assert {t.event_id for t in targets} == {"e9", "e10"}
    base = Candidate("full", [(req, Decimal("6000"))], total_paid=Decimal("6000"))
    assert not simulate(st, base.payments, {}).ok
    variants = spending_changes.find_variants(st, [base], targets)
    assert variants
    assert spending_changes.MAX_CHANGES == 3
    for v in variants:
        assert 1 <= len(v.changes) <= 3
        assert simulate(st, v.payments, v.changes).ok


# ---- Section 20: eligibility separation ----

def test_eligibility_keeps_unsafe_but_preferred():
    st = _state(opening=Decimal("100"), minimum=Decimal("1000"),
               requested=Decimal("500"), daily_net={})
    bad = Candidate("full", [(st.request_date, st.requested)], total_paid=st.requested)
    assert not simulate(st, bad.payments, {}).ok  # financially unsafe ...
    profile = {"methods_will_consider": ["full_payment"], "max_installment_months": None}
    assert filter_candidates([bad], profile, True, st.deadline) == [bad]  # ... yet passes filter


def test_eligibility_drops_safe_but_excluded_and_late_and_partial_gate():
    st = _state(daily_net={}, requested=Decimal("1500"))  # full today is safe
    good = Candidate("full", [(st.request_date, st.requested)], total_paid=st.requested)
    assert simulate(st, good.payments, {}).ok
    assert filter_candidates([good], {"methods_will_consider": ["installments"],
                                      "max_installment_months": 12}, True, st.deadline) == []
    late = Candidate("full", [(st.deadline + timedelta(days=1), st.requested)],
                     total_paid=st.requested)
    assert filter_candidates([late], {"methods_will_consider": ["full_payment"],
                                      "max_installment_months": None}, True, st.deadline) == []
    partial = Candidate("partial", [(st.request_date, Decimal("1")),
                                    (st.request_date, st.requested - 1)],
                        total_paid=st.requested)
    prof = {"methods_will_consider": ["partial_payment"], "max_installment_months": None}
    assert filter_candidates([partial], prof, False, st.deadline) == []
    assert filter_candidates([partial], prof, True, st.deadline) == [partial]


def test_wait_needs_full_acceptance():
    st = _state()
    wait = Candidate("wait", [(date(2025, 1, 20), st.requested)], total_paid=st.requested)
    no_full = {"methods_will_consider": ["installments"], "max_installment_months": 12}
    assert filter_candidates([wait], no_full, True, st.deadline) == []
    yes_full = {"methods_will_consider": ["full_payment"], "max_installment_months": None}
    assert filter_candidates([wait], yes_full, True, st.deadline) == [wait]


# ---- Section 21: optimizer remaining ties + decision mapping ----

def test_optimizer_earlier_start_fewer_payments_option_id():
    deadline = date(2025, 3, 10)
    early = Candidate("full", [(date(2025, 1, 10), Decimal("100"))], total_paid=Decimal("100"))
    late = Candidate("full", [(date(2025, 1, 20), Decimal("100"))], total_paid=Decimal("100"))
    assert optimizer.select([late, early], deadline) == early
    one = Candidate("installments", [(date(2025, 1, 10), Decimal("100"))],
                    option_id="opt_9", total_paid=Decimal("100"))
    two = Candidate("installments", [(date(2025, 1, 10), Decimal("50")),
                                     (date(2025, 2, 10), Decimal("50"))],
                    option_id="opt_1", total_paid=Decimal("100"))
    assert optimizer.select([two, one], deadline) == one
    a = Candidate("installments", [(date(2025, 1, 10), Decimal("100"))],
                  option_id="opt_b", total_paid=Decimal("100"))
    b = Candidate("installments", [(date(2025, 1, 10), Decimal("100"))],
                  option_id="opt_a", total_paid=Decimal("100"))
    assert optimizer.select([a, b], deadline) == b
    opt = Candidate("installments", [(date(2025, 1, 10), Decimal("100"))],
                    option_id="opt_1", total_paid=Decimal("100"))
    plain = Candidate("full", [(date(2025, 1, 10), Decimal("100"))], total_paid=Decimal("100"))
    assert optimizer.select([plain, opt], deadline) == opt  # None sorts last


def test_rules_derive_full_mapping():
    d = date(2025, 1, 10)
    assert decision_rules.derive(None) == ("not_affordable", "not_recommended")
    assert decision_rules.derive(
        Candidate("full", [(d, Decimal("1"))], total_paid=Decimal("1"))) == ("affordable_now", "full_payment")
    assert decision_rules.derive(
        Candidate("full", [(d, Decimal("1"))], total_paid=Decimal("1"),
                  changes={"e1": None})) == ("affordable_with_plan", "full_payment")
    assert decision_rules.derive(
        Candidate("partial", [(d, Decimal("1"))], total_paid=Decimal("1"))) == ("affordable_with_plan", "partial_payment")
    assert decision_rules.derive(
        Candidate("installments", [(d, Decimal("1"))], total_paid=Decimal("1"),
                  option_id="o")) == ("affordable_with_plan", "installments")
    assert decision_rules.derive(
        Candidate("wait", [(d, Decimal("1"))], total_paid=Decimal("1"))) == ("affordable_later", "wait")


# ---- Sections 39/40: LLM boundary + determinism ----

def test_no_llm_or_clock_in_deterministic_core():
    import pathlib
    core = ["forecast.py", "payment_plans.py", "optimizer.py", "spending_changes.py"]
    dec = ["eligibility.py", "rules.py", "decision.py", "invariants.py"]
    for rel in [f"src/affordai/finance/{n}" for n in core] + [f"src/affordai/decision/{n}" for n in dec]:
        text = pathlib.Path(rel).read_text(encoding="utf-8")
        for token in ("propose_facts", "llm_adapter", "openai", "anthropic",
                      "date.today", "datetime.now", "random."):
            assert token not in text, f"{rel} contains {token!r}"


def test_chain_deterministic_double_run():
    st = _state()
    profile = {"methods_will_consider": ["full_payment", "partial_payment", "installments"],
               "max_installment_months": 12}
    opt = _option()

    def run_once():
        safe = max_safe_today(st)
        earliest = earliest_full_date(st)
        cands, _ = payment_plans.generate(st, [opt], safe, earliest, True)
        eligible = filter_candidates(cands, profile, True, st.deadline)
        validated = [c for c in eligible if simulate(st, c.payments, c.changes or {}).ok]
        winner = optimizer.select(validated, st.deadline) if validated else None
        key = (str(safe), str(earliest),
               optimizer.rank_key(winner, st.deadline) if winner else None)
        return key

    assert run_once() == run_once()
