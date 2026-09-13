"""Regression snapshots: request_id -> compact decision signature."""
from __future__ import annotations

import json


def snapshot(decisions: list) -> dict:
    return {
        d.request_id: {
            "status": d.affordability_status,
            "method": d.recommended_payment_method,
            "safe": str(d.amount_safe_to_pay),
            "plan": d.payment_plan,
            "earliest": d.earliest_date_for_full_payment,
            "changes": d.spending_changes_needed,
        }
        for d in decisions
    }


def save(decisions: list, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshot(decisions), fh, indent=1, sort_keys=True)


def diff(old: dict, new: dict) -> list[str]:
    out = []
    for rid in sorted(set(old) | set(new)):
        if old.get(rid) != new.get(rid):
            out.append(rid)
    return out
