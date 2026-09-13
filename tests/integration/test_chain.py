"""Integration tests: module boundaries on synthetic fixtures."""
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, "src")

from affordai.decision import rules as decision_rules
from affordai.decision.decision import Decision
from affordai.decision.eligibility import filter_candidates
from affordai.finance import optimizer, payment_plans, spending_changes
from affordai.finance.currency import RateTable
from affordai.finance.forecast import earliest_full_date, max_safe_today, simulate
from affordai.finance.state import FinancialState
from affordai.output import explanation as explanation_mod
from affordai.output.serializer import decisions_to_rows, format_changes, format_plan
from affordai.output.validator import validate_files, validate_plans


def _ctx_state():
    state = FinancialState(
        request_id="r1",
        user_id="u1",
        request_date=date(2025, 1, 10),
        deadline=date(2025, 3, 10),
        home="INR",
        opening=Decimal("50000"),
        minimum=Decimal("5000"),
        requested=Decimal("20000"),
        flows=[],
        unknowns=[],
        notes=[],
        events_by_id={},
        daily_net={date(2025, 2, 10): Decimal("30000")},
    )
    options = [
        {
            "payment_option_id": "opt_1",
            "request_id": "r1",
            "payment_method": "installments",
            "payment_amount": Decimal("7000"),
            "number_of_payments": 3,
            "first_payment_date": date(2025, 1, 10),
            "payment_frequency_days": 30,
            "financing_fee": Decimal("1000"),
            "total_payable_amount": Decimal("21000"),
        }
    ]
    profile = {"methods_will_consider": ["full_payment", "installments"], "max_installment_months": 12,
               "willing_to_reduce": [], "willing_to_stop": []}
    return state, options, profile


def test_ingestion_to_decision_chain():
    state, options, profile = _ctx_state()
    safe = max_safe_today(state)
    assert safe == Decimal("20000")  # affordable today
    earliest = earliest_full_date(state)
    assert earliest == date(2025, 1, 10)
    cands, _ = payment_plans.generate(state, options, safe, earliest, True)
    assert {c.kind for c in cands} >= {"full", "installments"}
    eligible = filter_candidates(cands, profile, True, state.deadline)
    validated = [c for c in eligible if simulate(state, c.payments, {}).ok]
    winner = optimizer.select(validated, state.deadline)
    # full today, no changes, total 20000 < installments 21000 -> full wins
    assert winner.kind == "full"
    status, method = decision_rules.derive(winner)
    assert (status, method) == ("affordable_now", "full_payment")


def test_decision_to_output_to_validator(tmp_path):
    req_path = tmp_path / "requests.csv"
    req_path.write_text(
        "request_id,user_id,request_date,request_type,requested_amount,"
        "desired_completion_date,allows_partial_payment,request_text\n"
        "r1,u1,2025-01-10,purchase,20000,2025-03-10,true,buy\n",
        encoding="utf-8",
    )
    opt_path = tmp_path / "options.csv"
    opt_path.write_text(
        "payment_option_id,request_id,payment_method,payment_amount,number_of_payments,"
        "first_payment_date,payment_frequency_days,financing_fee,total_payable_amount\n",
        encoding="utf-8",
    )
    prof_path = tmp_path / "profiles.csv"
    prof_path.write_text(
        "user_id,home_currency,current_available_balance,minimum_balance_to_keep,"
        "financial_priorities,expense_categories_to_protect,"
        "expense_categories_user_is_willing_to_reduce,"
        "expense_categories_user_is_willing_to_stop,"
        "payment_methods_user_will_consider,max_installment_months\n"
        "u1,INR,50000,5000,,rent,,,full_payment,\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "output.csv"
    d = Decision(
        original_index=0, request_id="r1", user_id="u1",
        amount_safe_to_pay=Decimal("20000"),
        affordability_status="affordable_now",
        recommended_payment_method="full_payment",
        payment_plan=[(date(2025, 1, 10), Decimal("20000"))],
        earliest_date_for_full_payment="2025-01-10",
        spending_changes_needed={},
        decision_explanation="",
        evidence=[],
    )
    d.decision_explanation = explanation_mod.build(d, "20000", "2025-01-10", "INR")
    assert explanation_mod.validate(d.decision_explanation, d)
    import csv

    rows = decisions_to_rows([d], {"r1": "INR"})
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    assert validate_files(str(req_path), str(out_path)) == []
    assert validate_plans(str(req_path), str(opt_path), str(prof_path), str(out_path)) == []


def test_spending_change_flips_safety():
    state = FinancialState(
        request_id="r1", user_id="u1",
        request_date=date(2025, 1, 10), deadline=date(2025, 3, 10),
        home="INR", opening=Decimal("12000"), minimum=Decimal("5000"),
        requested=Decimal("6000"), flows=[], unknowns=[], notes=[],
        events_by_id={
            "e9": {"event_id": "e9", "flexibility": "stoppable", "category": "streaming",
                   "event_type": "subscription", "minimum_allowed_amount": None},
        },
        daily_net={},
    )
    from affordai.finance.timeline import Flow

    state.flows = [
        Flow(date(2025, 1, 12), Decimal("-4000"), "inferred", None, "e9", "streaming", "stoppable", False),
        Flow(date(2025, 2, 12), Decimal("-4000"), "inferred", None, "e9", "streaming", "stoppable", False),
    ]
    state.daily_net = {date(2025, 1, 12): Decimal("-4000"), date(2025, 2, 12): Decimal("-4000")}
    base = payment_plans.Candidate("full", [(date(2025, 1, 10), Decimal("6000"))], total_paid=Decimal("6000"))
    assert not simulate(state, base.payments, {}).ok
    profile = {"willing_to_reduce": [], "willing_to_stop": ["streaming"]}
    targets = spending_changes.candidate_targets(state, profile)
    assert targets and targets[0].event_id == "e9"
    variants = spending_changes.find_variants(state, [base], targets)
    assert variants and simulate(state, variants[0].payments, variants[0].changes).ok
    assert format_changes(variants[0].changes, "INR") == "stop:e9"
