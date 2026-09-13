"""Output schema + contract validator.

Structural layer (validate_files): columns/order/count/IDs/bounds/enums/
status-method/earliest consistency.
Plan layer (validate_plans): chronology, totals, partial 5-conditions,
installment exact-option match, wait shape, spending-change syntax/rules,
deadline gate. Independent of engine internals: re-derives every check
from the CSVs. Preference acceptance (methods_will_consider) is checked
here too via profiles.
"""
from __future__ import annotations

import csv
from datetime import datetime

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


def _parse_plan(plan: str, rid: str, errors: list[str]) -> list[tuple] | None:
    """Parse YYYY-MM-DD:amount|... ; 'none' -> []. None on malformed."""
    if plan == "none":
        return []
    legs: list[tuple] = []
    for leg in plan.split("|"):
        parts = leg.split(":")
        if len(parts) != 2:
            errors.append(f"{rid}: malformed plan leg {leg!r}")
            return None
        try:
            day = datetime.strptime(parts[0], "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"{rid}: bad plan date {parts[0]!r}")
            return None
        try:
            amount = float(parts[1])
        except ValueError:
            errors.append(f"{rid}: bad plan amount {parts[1]!r}")
            return None
        if amount <= 0:
            errors.append(f"{rid}: non-positive plan amount {parts[1]!r}")
            return None
        legs.append((day, amount))
    if [d for d, _ in legs] != sorted(d for d, _ in legs):
        errors.append(f"{rid}: plan not chronological")
        return None
    return legs


def validate_plans(
    requests_path: str, options_path: str, profiles_path: str, output_path: str
) -> list[str]:
    """Plan/financial layer: independent re-derivation from CSVs."""
    errors: list[str] = []
    req_rows = {r["request_id"]: r for r in csv.DictReader(open(requests_path, encoding="utf-8-sig"))}
    out_rows = list(csv.DictReader(open(output_path, encoding="utf-8-sig")))
    options: dict[str, list[dict]] = {}
    for o in csv.DictReader(open(options_path, encoding="utf-8-sig")):
        options.setdefault(o["request_id"], []).append(o)
    profiles = {r["user_id"]: r for r in csv.DictReader(open(profiles_path, encoding="utf-8-sig"))}

    for out in out_rows:
        rid = out.get("request_id", "")
        req = req_rows.get(rid)
        if req is None:
            continue
        try:
            requested = float(req["requested_amount"])
            safe = float(out.get("amount_safe_to_pay", ""))
        except ValueError:
            continue  # reported by structural layer
        status = out.get("affordability_status", "")
        method = out.get("recommended_payment_method", "")
        earliest = out.get("earliest_date_for_full_payment", "")
        deadline = req["desired_completion_date"]
        req_date = req["request_date"]
        legs = _parse_plan(out.get("payment_plan", ""), rid, errors)
        if legs is None:
            continue

        if method == "not_recommended":
            if legs:
                errors.append(f"{rid}: not_recommended must have plan none")
            if out.get("spending_changes_needed", "") != "none":
                errors.append(f"{rid}: not_recommended must have changes none")
            continue
        if not legs:
            errors.append(f"{rid}: {method} needs a dated plan")
            continue
        if legs[-1][0].isoformat() > deadline:
            errors.append(f"{rid}: plan completes after desired_completion_date")
        total = round(sum(a for _, a in legs), 2)

        if method == "full_payment":
            if len(legs) != 1 or legs[0][0].isoformat() != req_date or abs(total - requested) > 0.005:
                errors.append(f"{rid}: full_payment must be request_date:requested")
            if status == "affordable_now" and (
                legs[0][0].isoformat() != req_date or abs(safe - requested) > 0.005
            ):
                errors.append(f"{rid}: affordable_now needs safe==requested on request_date")
        elif method == "partial_payment":
            allows = str(req["allows_partial_payment"]).strip().lower() == "true"
            if not allows:
                errors.append(f"{rid}: partial_payment not allowed by request")
            if len(legs) != 2:
                errors.append(f"{rid}: partial_payment needs exactly 2 payments")
            elif (
                legs[0][0].isoformat() != req_date
                or abs(legs[0][1] - safe) > 0.005
                or legs[1][0].isoformat() != earliest
                or abs(total - requested) > 0.005
                or not (0 < safe < requested)
                or (earliest and earliest > deadline)
            ):
                errors.append(f"{rid}: partial_payment shape violated")
        elif method == "installments":
            match = False
            for o in options.get(rid, []):
                if o["payment_method"] != "installments":
                    continue
                try:
                    count = int(o["number_of_payments"])
                    amount = float(o["payment_amount"])
                except ValueError:
                    continue
                from datetime import timedelta as _td

                try:
                    first = datetime.strptime(o["first_payment_date"], "%Y-%m-%d").date()
                    freq = int(o["payment_frequency_days"] or "0")
                except ValueError:
                    continue
                expected = [(first + _td(days=freq * k), amount) for k in range(count)]
                if (
                    len(legs) == len(expected)
                    and all(
                        l[0] == e[0] and abs(l[1] - e[1]) < 0.005
                        for l, e in zip(legs, expected)
                    )
                ):
                    match = True
                    break
            if not match:
                errors.append(f"{rid}: installments must exactly match a supplied option")
        elif method == "wait":
            if (
                len(legs) != 1
                or legs[0][0].isoformat() != earliest
                or abs(total - requested) > 0.005
                or not earliest
                or earliest <= req_date
            ):
                errors.append(f"{rid}: wait must be a single future payment on earliest")

        # Spending changes: none | <=3 stop:/reduce_to:, no same-event dup.
        changes = out.get("spending_changes_needed", "")
        if changes != "none":
            parts = changes.split("|")
            if len(parts) > 3:
                errors.append(f"{rid}: more than 3 spending changes")
            seen_events: set[str] = set()
            for part in parts:
                segs = part.split(":")
                if segs[0] == "stop" and len(segs) == 2 and segs[1]:
                    eid = segs[1]
                elif (
                    len(segs) == 3 and segs[0] == "reduce_to" and segs[1]
                ):
                    eid = segs[1]
                    try:
                        new_amount = float(segs[2])
                    except ValueError:
                        errors.append(f"{rid}: bad reduce_to amount {part!r}")
                        continue
                    if new_amount < 0:
                        errors.append(f"{rid}: negative reduce_to {part!r}")
                else:
                    errors.append(f"{rid}: malformed spending change {part!r}")
                    continue
                if eid in seen_events:
                    errors.append(f"{rid}: stop+reduce on same event {eid}")
                seen_events.add(eid)

        # Preference acceptance (independent of engine).
        prof = profiles.get(req["user_id"], {})
        accepted = {p.strip() for p in str(prof.get("payment_methods_user_will_consider", "")).replace(";", ",").replace("|", ",").split(",") if p.strip()}
        need = {"full_payment": "full_payment", "partial_payment": "partial_payment", "installments": "installments", "wait": "full_payment"}.get(method)
        if need and need not in accepted:
            errors.append(f"{rid}: method {method} not accepted by user")
    return errors
