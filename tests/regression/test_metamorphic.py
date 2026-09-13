"""Metamorphic regression guards on live data (subset for speed).

M1 row-order: shuffled input rows -> identical per-request decisions.
M2 irrelevant evidence: junk message -> same decision.
M3 balance monotonicity: +5000 opening -> safe never decreases.
"""
import sys
from copy import deepcopy
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, "src")

from affordai.pipeline import build_contexts, decide_context, load_dataset


def _subset(n=6):
    tables = load_dataset("dataset/official")
    return tables, build_contexts(tables)[:n]


def _sig(d):
    return (
        d.affordability_status,
        d.recommended_payment_method,
        d.amount_safe_to_pay,
        d.payment_plan,
        d.earliest_date_for_full_payment,
        d.spending_changes_needed,
    )


def test_m1_row_order_invariance():
    import random

    tables, ctxs = _subset()
    base = {c.request_id: _sig(decide_context(c, tables, "dataset/official")) for c in ctxs}
    rows = list(tables["requests"])
    random.Random(7).shuffle(rows)
    tables2 = dict(tables, requests=rows)
    by_id = {c.request_id: c for c in build_contexts(tables2)}
    for c in ctxs:
        assert _sig(decide_context(by_id[c.request_id], tables2, "dataset/official")) == base[c.request_id]


def test_m2_irrelevant_evidence_invariance():
    tables, ctxs = _subset()
    c0 = ctxs[0]
    d_base = decide_context(c0, tables, "dataset/official")
    cb = deepcopy(c0)
    cb.messages = list(c0.messages) + [{
        "message_id": "junk-1", "user_id": c0.user_id, "request_id": None,
        "related_event_id": None, "sent_at": datetime(2025, 1, 1),
        "source_type": "merchant", "message_text": "Thanks for shopping with us!",
    }]
    d_junk = decide_context(cb, tables, "dataset/official")
    assert _sig(d_junk) == _sig(d_base)


def test_m3_balance_monotonicity():
    tables, ctxs = _subset()
    for c in ctxs:
        d_base = decide_context(c, tables, "dataset/official")
        ch = deepcopy(c)
        ch.profile = dict(c.profile, current_available_balance=c.profile["current_available_balance"] + Decimal("5000"))
        d_hi = decide_context(ch, tables, "dataset/official")
        assert d_hi.amount_safe_to_pay >= d_base.amount_safe_to_pay
