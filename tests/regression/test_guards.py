"""Regression guards: past failures must stay fixed.

R1 (Tier-1 earliest): not_affordable MAY carry a real earliest date.
R2 (row identity): validator rejects reordered/duplicate request_ids.
R3 (payroll refs): 'payroll EMP-0001' style refs never parse as amounts.
R4 (preference split): 'a|b' method lists split on pipes.
R5 (sent_at): ISO datetimes parse; row order preserved by (sent_at, id).
"""
import sys
from datetime import datetime

sys.path.insert(0, "src")

from affordai.decision.invariants import check_earliest_consistency
from affordai.evidence.message_interpreter import interpret
from affordai.ingestion import parse_datetime
from affordai.ingestion.profiles import _split_list
from affordai.output.validator import validate_files


def test_r1_earliest_with_not_affordable():
    assert check_earliest_consistency("not_affordable", "2025-11-06", "2026-01-15")


def test_r2_reordered_and_duplicate_rows_rejected(tmp_path):
    req = tmp_path / "requests.csv"
    req.write_text(
        "request_id,user_id,request_date,request_type,requested_amount,"
        "desired_completion_date,allows_partial_payment,request_text\n"
        "r1,u1,2025-01-10,purchase,100,2025-03-10,true,x\n"
        "r2,u1,2025-01-10,purchase,100,2025-03-10,true,x\n",
        encoding="utf-8",
    )
    bad_order = tmp_path / "bad.csv"
    bad_order.write_text(
        "request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,"
        "payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation\n"
        "r2,100,affordable_now,full_payment,2025-01-10:100,2025-01-10,none,e\n"
        "r1,100,affordable_now,full_payment,2025-01-10:100,2025-01-10,none,e\n",
        encoding="utf-8",
    )
    assert validate_files(str(req), str(bad_order))
    dup = tmp_path / "dup.csv"
    dup.write_text(
        "request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,"
        "payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation\n"
        "r1,100,affordable_now,full_payment,2025-01-10:100,2025-01-10,none,e\n"
        "r1,100,affordable_now,full_payment,2025-01-10:100,2025-01-10,none,e\n",
        encoding="utf-8",
    )
    assert validate_files(str(req), str(dup))


def test_r3_payroll_ref_no_amount():
    msg = {
        "message_id": "m", "user_id": "u", "request_id": "r",
        "related_event_id": None,
        "message_text": "Ref payroll EMP-0001. See case SER-0007.",
    }
    assert [f for f in interpret(msg) if f.kind == "amend_amount"] == []


def test_r4_pipe_split():
    assert _split_list("full_payment|partial_payment") == ["full_payment", "partial_payment"]


def test_r5_sent_at_ordering():
    a = parse_datetime("2025-07-29T09:30:00Z", "t")
    b = parse_datetime("2025-07-29", "t")
    assert isinstance(a, datetime) and a > b


def test_r6_per_request_fallback_never_crashes_batch():
    from affordai.pipeline import RequestContext, _decide_safe

    broken = RequestContext(
        original_index=0, request_id="rx", user_id="ux",
        request={"request_id": "rx"}, profile={}, events=[],
        messages=[], images=[], payment_options=[],
    )
    decision, failed = _decide_safe(broken, {}, "dataset/official", None, None)
    assert failed is True
    assert decision.affordability_status == "not_affordable"
    assert decision.recommended_payment_method == "not_recommended"
    assert decision.payment_plan == "none"
    assert decision.original_index == 0  # identity preserved on fallback
