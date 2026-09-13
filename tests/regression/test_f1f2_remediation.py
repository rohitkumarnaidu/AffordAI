"""F1/F2 remediation regression (YELLOW->GREEN).

F1: validator._parse_plan duplicate removed - exactly one authoritative def,
    Decimal-strict behavior preserved.
F2: engine.evaluate_and_select allows_partial explicit - no hardcoded True,
    partial allowed/rejected per request, production pipeline unaffected.
"""
import inspect
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, "src")


def test_f1_single_parse_plan_authoritative():
    import affordai.output.validator as v

    src = inspect.getsource(v)
    assert src.count("def _parse_plan") == 1, "duplicate _parse_plan remains"
    # Decimal-strict behavior: NaN/Infinity rejected, coded errors
    errs: list = []
    assert v._parse_plan("none", "r", errs) == []
    errs.clear()
    assert v._parse_plan("2025-01-10:abc", "r", errs) is None
    assert any("OUTPUT-NUM-001" in e for e in errs)
    errs.clear()
    assert v._parse_plan("2025-01-20:50|2025-01-10:50", "r", errs) is None
    assert any("OUTPUT-PLAN-003" in e for e in errs)
    errs.clear()
    legs = v._parse_plan("2025-01-10:100|2025-02-10:100", "r", errs)
    assert errs == [] and len(legs) == 2


def _cand_state():
    from affordai.finance.state import FinancialState

    return FinancialState(
        request_id="r-f", user_id="u-f", request_date=date(2025, 1, 10),
        deadline=date(2025, 3, 10), home="INR", opening=Decimal("10000"),
        minimum=Decimal("100"), requested=Decimal("100"), flows=[],
        unknowns=[], notes=[], events_by_id={}, daily_net={},
    )


def test_f2_allows_partial_explicit_no_bypass():
    from affordai.decision.engine import evaluate_and_select
    from affordai.finance.payment_plans import Candidate

    sig = inspect.signature(evaluate_and_select)
    assert "allows_partial" in sig.parameters, "allows_partial param missing"
    assert sig.parameters["allows_partial"].default is False, "default must be False (fail-closed)"

    st = _cand_state()
    partial = Candidate("partial", [(date(2025, 1, 10), Decimal("40")), (date(2025, 1, 20), Decimal("60"))],
                        total_paid=Decimal("100"))
    profile = {"methods_will_consider": ["partial_payment"], "max_installment_months": None}
    # Allowed -> kept (if safe)
    validated_on, _ = evaluate_and_select(st, [partial], profile, st.deadline, allows_partial=True)
    assert partial in validated_on
    # Rejected -> dropped (preference bypass impossible)
    validated_off, winner_off = evaluate_and_select(st, [partial], profile, st.deadline, allows_partial=False)
    assert validated_off == [] and winner_off is None


def test_f2_production_pipeline_unaffected():
    import pathlib

    pipe = pathlib.Path("src/affordai/pipeline.py").read_text(encoding="utf-8")
    # Production path calls filter_candidates directly with real request flag, never engine helper
    assert "from affordai.decision.engine import" not in pipe
    assert "evaluate_and_select" not in pipe
    assert 'filter_candidates(' in pipe
