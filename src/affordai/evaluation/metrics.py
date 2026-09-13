"""Local-proxy metrics vs sample_requests.csv (NOT official score)."""
from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal


def compare(decisions: list, sample_path: str) -> dict:
    expected = {r["request_id"]: r for r in csv.DictReader(open(sample_path, encoding="utf-8-sig"))}
    got = {d.request_id: d for d in decisions if d.request_id in expected}
    status_ok = sum(1 for rid, d in got.items() if d.affordability_status == expected[rid]["affordability_status"])
    method_ok = sum(1 for rid, d in got.items() if d.recommended_payment_method == expected[rid]["recommended_payment_method"])
    earliest_ok = sum(
        1
        for rid, d in got.items()
        if d.earliest_date_for_full_payment == expected[rid]["earliest_date_for_full_payment"]
    )
    abs_err = []
    for rid, d in got.items():
        try:
            exp = Decimal(expected[rid]["amount_safe_to_pay"] or "0")
            abs_err.append(abs(d.amount_safe_to_pay - exp))
        except Exception:
            continue
    mae = sum(abs_err, Decimal("0")) / len(abs_err) if abs_err else Decimal("0")
    return {
        "n_compared": len(got),
        "status_accuracy": status_ok / len(got) if got else 0.0,
        "method_accuracy": method_ok / len(got) if got else 0.0,
        "earliest_exact": earliest_ok / len(got) if got else 0.0,
        "safe_mae": str(mae),
        "status_mix": dict(Counter(d.affordability_status for d in got.values())),
        "method_mix": dict(Counter(d.recommended_payment_method for d in got.values())),
    }
