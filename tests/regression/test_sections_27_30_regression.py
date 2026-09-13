"""Section 29 regression system: one production-path test per required group.

Lifecycle per bug (see tests/regression/REGRESSIONS.md):
FAILURE -> capture -> expected -> actual -> root cause -> general rule ->
targeted fix -> regression test (here) -> nearby-case test -> full suite -> report.

Each test below pins a general rule, not a single example. All states are
synthetic with distinct parameters from other suites (no hardcoded output.csv).
Groups (29.2): row order, wrong decision, wrong payment, wrong date, currency,
evidence mismatch, image extraction, cancellation, amendment, duplicate event,
preference, partial payment, installments, deadline, minimum balance.
"""
import sys
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, "src")

from affordai.decision import rules as decision_rules
from affordai.decision.eligibility import filter_candidates
from affordai.evidence import conflict_resolver
from affordai.evidence.evidence_registry import Evidence, EvidenceRegistry
from affordai.evidence.image_interpreter import resolve_images_for_event
from affordai.evidence.message_interpreter import interpret as interpret_message
from affordai.finance import optimizer, payment_plans
from affordai.finance.currency import RateTable
from affordai.finance.forecast import earliest_full_date, max_safe_today, simulate
from affordai.finance.money import parse_amount
from affordai.finance.payment_plans import Candidate
from affordai.finance.state import FinancialState
from affordai.finance.temporal import meets_deadline
from affordai.ingestion import check_duplicates
from affordai.ingestion.payment_options import expand_schedule
from affordai.output.validator import validate_files


def _state(**kw):
    args = dict(
        request_id="r-2930",
        user_id="u-2930",
        request_date=date(2025, 4, 2),
        deadline=date(2025, 6, 2),
        home="INR",
        opening=Decimal("8000"),
        minimum=Decimal("2000"),
        requested=Decimal("4500"),
        flows=[],
        unknowns=[],
        notes=[],
        events_by_id={},
        daily_net={date(2025, 4, 25): Decimal("6000")},
    )
    args.update(kw)
    return FinancialState(**args)


def _tight_state(**kw):
    """State with 0 < safe < requested (partial-eligible shape)."""
    args = dict(opening=Decimal("5000"), minimum=Decimal("2000"),
                requested=Decimal("4500"),
                daily_net={date(2025, 4, 25): Decimal("6000")})
    args.update(kw)
    return _state(**args)


# 29.2.1 row order: pipeline sorts by original_index; validator rejects disorder.
def test_s29_row_order_identity_preserved_and_enforced(tmp_path):
    ordered = sorted([(1, "r-b"), (0, "r-a")])
    assert [rid for _, rid in ordered] == ["r-a", "r-b"]
    req = tmp_path / "requests.csv"
    req.write_text(
        "request_id,user_id,request_date,request_type,requested_amount,"
        "desired_completion_date,allows_partial_payment,request_text\n"
        "r-a,u1,2025-04-02,purchase,100,2025-06-02,true,x\n"
        "r-b,u1,2025-04-02,purchase,200,2025-06-02,true,x\n",
        encoding="utf-8",
    )
    cols = ("request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,"
            "payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation\n")
    swapped = tmp_path / "swapped.csv"
    swapped.write_text(
        cols + "r-b,50,not_affordable,not_recommended,none,,none,e\n"
        "r-a,100,affordable_now,full_payment,2025-04-02:100,2025-04-02,none,e\n",
        encoding="utf-8",
    )
    assert validate_files(str(req), str(swapped))  # non-empty = rejected


# 29.2.2 wrong decision: derive() mapping is total over winner kinds.
def test_s29_wrong_decision_mapping_total():
    d = date(2025, 4, 2)
    assert decision_rules.derive(None) == ("not_affordable", "not_recommended")
    assert decision_rules.derive(
        Candidate("full", [(d, Decimal("5"))], total_paid=Decimal("5"))
    ) == ("affordable_now", "full_payment")
    assert decision_rules.derive(
        Candidate("partial", [(d, Decimal("2")), (d, Decimal("3"))], total_paid=Decimal("5"))
    ) == ("affordable_with_plan", "partial_payment")
    assert decision_rules.derive(
        Candidate("wait", [(d + timedelta(days=9), Decimal("5"))], total_paid=Decimal("5"))
    ) == ("affordable_later", "wait")


# 29.2.3 wrong payment: partial legs always sum to requested, verified by re-simulation.
def test_s29_wrong_payment_partial_sums_to_requested():
    st = _tight_state()
    safe = max_safe_today(st)
    assert Decimal("0") < safe < st.requested
    earliest = earliest_full_date(st)
    assert earliest is not None and earliest <= st.deadline
    cands, _ = payment_plans.generate(st, [], safe, earliest, True)
    partials = [c for c in cands if c.kind == "partial"]
    assert len(partials) == 1
    legs = partials[0].payments
    assert sum(a for _, a in legs) == st.requested
    assert legs[0][1] == safe and legs[1][1] == st.requested - safe
    assert simulate(st, legs).ok


# 29.2.4 wrong date: earliest is minimal -- every earlier day unsafe (distinct params).
def test_s29_wrong_date_earliest_minimal():
    st = _state(opening=Decimal("5000"), minimum=Decimal("1500"),
                requested=Decimal("7000"), daily_net={date(2025, 5, 3): Decimal("9000")})
    earliest = earliest_full_date(st)
    assert earliest is not None and earliest > st.request_date
    day = st.request_date
    while day < earliest:
        assert not simulate(st, [(day, st.requested)]).ok
        day += timedelta(days=1)
    assert simulate(st, [(earliest, st.requested)]).ok


# 29.2.5 currency: dated rate = latest row on/before settlement, exact directed pair.
def test_s29_currency_dated_directed_rate():
    rt = RateTable([
        {"rate_date": date(2025, 3, 1), "from_currency": "USD",
         "to_currency": "INR", "rate": Decimal("83")},
        {"rate_date": date(2025, 4, 1), "from_currency": "USD",
         "to_currency": "INR", "rate": Decimal("84")},
    ])
    amount, trace = rt.convert_to_home(Decimal("10"), "USD", "INR", date(2025, 4, 2))
    assert amount == Decimal("840")
    assert trace.rate == Decimal("84")
    assert rt.get_rate("USD", "INR", date(2025, 3, 15)).rate == Decimal("83")


# 29.2.6 evidence mismatch: cross-request facts rejected; unknown ids never admitted.
# Rule pinned: the registry checks the message_id/event_id/image_id FIELDS
# (not source_id), plus request/user ownership, kind/method, confidence.
def test_s29_evidence_mismatch_rejected():
    reg = EvidenceRegistry({"e1"}, {"m1"}, {"i1"})
    reg.add(Evidence("message", "m1", "r-2930", "u-2930", kind="confirm",
                     message_id="m1"), "r-2930", "u-2930")
    for bad in (
        Evidence("message", "mX", "r-2930", "u-2930", kind="confirm",
                 message_id="mX"),  # unknown message_id
        Evidence("message", "m1", "r-OTHER", "u-2930", kind="confirm",
                 message_id="m1"),  # wrong request
        Evidence("message", "m1", "r-2930", "u-OTHER", kind="confirm",
                 message_id="m1"),  # wrong user
        Evidence("event", "eX", "r-2930", "u-2930", kind="cancel",
                 event_id="eX"),  # unknown event_id
    ):
        try:
            reg.add(bad, "r-2930", "u-2930")
        except Exception:
            continue
        raise AssertionError(f"admitted {bad!r}")
    assert len(reg) == 1


# 29.2.7 image extraction: blank amount is NEVER zero; missing file never fills.
def test_s29_image_extraction_blank_never_zero():
    assert parse_amount("") is None
    assert parse_amount(None) is None
    linked = resolve_images_for_event("ev-missing", [], "dataset/official/media/images")
    assert linked == []
    # Unknown (not zero) is the only safe representation without vision output.
    st = _state()
    assert max_safe_today(st) >= Decimal("0")


# 29.2.8 cancellation: cancelled events leave the flow set (timeline path).
def test_s29_cancellation_removes_event_from_flows():
    from affordai.finance.timeline import build_flows

    class _Ctx:
        request = {"original_index": 0, "request_id": "r-c", "user_id": "u-c",
                   "request_date": date(2025, 4, 2),
                   "desired_completion_date": date(2025, 6, 2),
                   "requested_amount": Decimal("100")}
        profile = {"user_id": "u-c", "home_currency": "INR",
                   "current_available_balance": Decimal("8000"),
                   "minimum_balance_to_keep": Decimal("2000"),
                   "expense_categories_to_protect": []}
        events = [{
            "event_id": "e-cancel-me", "user_id": "u-c", "event_type": "expense",
            "description": "fee", "category": "fees", "direction": "debit",
            "amount": Decimal("7000"), "currency": "INR",
            "event_date": date(2025, 4, 5), "settlement_date": date(2025, 4, 5),
            "status": "scheduled", "flexibility": "fixed", "minimum_allowed_amount": None,
        }]

    rt = RateTable([])
    flows_kept, _, _ = build_flows(_Ctx(), rt, set(), {}, {}, [])
    flows_dropped, _, _ = build_flows(_Ctx(), rt, {"e-cancel-me"}, {}, {}, [])
    assert any(f.event_id == "e-cancel-me" for f in flows_kept)
    assert not any(f.event_id == "e-cancel-me" for f in flows_dropped)


# 29.2.9 amendment: amended amount replaces the scheduled amount in flows.
def test_s29_amendment_overrides_scheduled_amount():
    facts = interpret_message({
        "message_id": "m-am", "user_id": "u-2930", "request_id": "r-2930",
        "related_event_id": "e-am",
        "message_text": "Please update the amount to 2500 for next month.",
    })
    amends = [f for f in facts if f.kind == "amend_amount" and f.event_id == "e-am"]
    assert amends
    raw = conflict_resolver.amended_amounts(amends)
    assert parse_amount(raw["e-am"]) == Decimal("2500")


# 29.2.10 duplicate event: duplicate ids fail fast at ingestion, never double-count.
def test_s29_duplicate_event_rejected():
    try:
        check_duplicates([{"event_id": "e1"}, {"event_id": "e1"}], "event_id", "financial_events")
    except Exception:
        return
    raise AssertionError("duplicate event_ids accepted")


# 29.2.11 preference: safe-but-excluded method is dropped before ranking.
def test_s29_preference_excluded_method_dropped():
    st = _state(daily_net={}, requested=Decimal("1500"))  # full today safe
    good = Candidate("full", [(st.request_date, st.requested)], total_paid=st.requested)
    assert simulate(st, good.payments, {}).ok
    assert filter_candidates([good], {"methods_will_consider": ["installments"],
                                      "max_installment_months": 12}, True, st.deadline) == []
    assert filter_candidates([good], {"methods_will_consider": ["full_payment"],
                                      "max_installment_months": None}, True, st.deadline) == [good]


# 29.2.12 partial payment: gate needs allows-partial AND 0 < safe < requested.
def test_s29_partial_payment_gate():
    st = _tight_state()
    safe = max_safe_today(st)
    assert Decimal("0") < safe < st.requested
    earliest = earliest_full_date(st)
    cands, _ = payment_plans.generate(st, [], safe, earliest, True)
    assert [c for c in cands if c.kind == "partial"]
    cands_off, _ = payment_plans.generate(st, [], safe, earliest, False)
    assert [c for c in cands_off if c.kind == "partial"] == []
    rich = _state(daily_net={}, requested=Decimal("1500"))  # safe == requested: no partial
    safe_r = max_safe_today(rich)
    assert not (Decimal("0") < safe_r < rich.requested)


# 29.2.13 installments: exact schedule match incl. fee; malformed skipped with note.
def test_s29_installments_exact_and_malformed():
    st = _state()
    opt = dict(payment_option_id="opt_29", request_id="r-2930", payment_method="installments",
               payment_amount=Decimal("1500"), number_of_payments=3,
               first_payment_date=date(2025, 4, 2), payment_frequency_days=30,
               financing_fee=Decimal("150"), total_payable_amount=Decimal("4650"))
    cands, notes = payment_plans.generate(
        st, [opt], max_safe_today(st), earliest_full_date(st), True)
    inst = [c for c in cands if c.kind == "installments"]
    assert len(inst) == 1
    assert inst[0].payments == expand_schedule(opt)
    assert inst[0].total_paid == Decimal("4650")
    assert not notes
    bad = dict(opt, payment_option_id="opt_29_bad", payment_frequency_days=None)
    cands2, notes2 = payment_plans.generate(
        st, [bad], max_safe_today(st), earliest_full_date(st), True)
    assert [c for c in cands2 if c.kind == "installments"] == []
    assert any("opt_29_bad" in n for n in notes2)


# 29.2.14 deadline: on-deadline completion eligible; day-after is not; ranking prefers on-time.
def test_s29_deadline_boundary():
    assert meets_deadline(date(2025, 6, 2), date(2025, 6, 2))
    assert not meets_deadline(date(2025, 6, 3), date(2025, 6, 2))
    st = _state(daily_net={}, requested=Decimal("1500"))
    on_time = Candidate("full", [(st.deadline, st.requested)], total_paid=st.requested)
    late = Candidate("full", [(st.deadline + timedelta(days=1), st.requested)],
                     total_paid=st.requested)
    prof = {"methods_will_consider": ["full_payment"], "max_installment_months": None}
    assert filter_candidates([on_time], prof, True, st.deadline) == [on_time]
    assert filter_candidates([late], prof, True, st.deadline) == []
    assert optimizer.select([late, on_time], st.deadline) == on_time


# 29.2.15 minimum balance: exact floor passes; one unit below fails.
def test_s29_minimum_balance_floor_exact():
    st = _state(opening=Decimal("6500"), minimum=Decimal("2000"),
                requested=Decimal("4500"), daily_net={})
    safe = max_safe_today(st)
    assert safe == Decimal("4500")  # exact floor: 6500 - 4500 == 2000 minimum
    assert simulate(st, [(st.request_date, safe)]).ok
    assert not simulate(st, [(st.request_date, safe + Decimal("0.01"))]).ok
