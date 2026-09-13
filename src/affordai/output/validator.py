"""Output schema + contract validator (Milestone 1: structural layer)."""
from __future__ import annotations

import csv

from affordai.decision.decision import METHODS, OUTPUT_COLUMNS, STATUSES
from affordai.decision.invariants import (
    check_amount_bounds,
    check_earliest_consistency,
    check_status_method_consistency,
)


def validate_files(requests_path: str, output_path: str) -> list[str]:
    errors: list[str] = []
    with open(requests_path, newline="", encoding="utf-8") as f:
        req_rows = list(csv.DictReader(f))
    with open(output_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != OUTPUT_COLUMNS:
            errors.append(f"columns: expected {OUTPUT_COLUMNS}, got {reader.fieldnames}")
        out_rows = list(reader)
    if len(out_rows) != len(req_rows):
        errors.append(f"row count: requests={len(req_rows)} output={len(out_rows)}")
    req_by_id = {r["request_id"]: (i, r) for i, r in enumerate(req_rows)}
    seen: set[str] = set()
    for i, (req, out) in enumerate(zip(req_rows, out_rows)):
        rid = out.get("request_id", "")
        if rid != req["request_id"]:
            errors.append(f"row {i}: order mismatch output={rid} requests={req['request_id']}")
        if rid in seen:
            errors.append(f"row {i}: duplicate request_id {rid}")
        seen.add(rid)
        try:
            safe = float(out.get("amount_safe_to_pay", ""))
            requested = float(req["requested_amount"])
        except ValueError:
            errors.append(f"row {i} ({rid}): non-numeric safe/requested")
            continue
        if not check_amount_bounds(safe, requested):
            errors.append(f"row {i} ({rid}): 0 <= {safe} <= {requested} violated")
        if out.get("affordability_status") not in STATUSES:
            errors.append(f"row {i} ({rid}): bad status {out.get('affordability_status')}")
        if out.get("recommended_payment_method") not in METHODS:
            errors.append(f"row {i} ({rid}): bad method {out.get('recommended_payment_method')}")
        if not check_status_method_consistency(
            out.get("affordability_status", ""), out.get("recommended_payment_method", "")
        ):
            errors.append(f"row {i} ({rid}): status/method inconsistent")
        if not check_earliest_consistency(
            out.get("affordability_status", ""),
            req.get("request_date", ""),
            out.get("earliest_date_for_full_payment", ""),
        ):
            errors.append(f"row {i} ({rid}): earliest-date inconsistent")
    missing = set(req_by_id) - seen
    if missing:
        errors.append(f"missing request_ids: {sorted(missing)[:5]}")
    return errors
