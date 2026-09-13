"""End-to-end pipeline entry point.

Milestone 1: emits a schema-valid placeholder skeleton (NOT final decisions).
Milestone 2+: deterministic financial engine replaces the placeholder per request.
"""
from __future__ import annotations

import argparse
import csv
import sys

sys.path.insert(0, "src")

from affordai.decision.decision import OUTPUT_COLUMNS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset/official")
    ap.add_argument("--out", default="output.csv")
    args = ap.parse_args()
    with open(f"{args.dataset}/requests.csv", newline="", encoding="utf-8") as f:
        requests = list(csv.DictReader(f))
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        w.writeheader()
        for r in requests:
            w.writerow(
                {
                    "request_id": r["request_id"],
                    "amount_safe_to_pay": 0,
                    "affordability_status": "not_affordable",
                    "recommended_payment_method": "not_recommended",
                    "payment_plan": "none",
                    "earliest_date_for_full_payment": "",
                    "spending_changes_needed": "none",
                    "decision_explanation": "Placeholder baseline pending Milestone 2 engine.",
                }
            )
    print(f"wrote {len(requests)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
