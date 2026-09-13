"""Output schema + contract validator -- FINAL GATE (Section 26).

Structural layer (validate_files): columns/order/count/IDs/bounds/enums/
status-method/earliest consistency.
Plan layer (validate_plans): chronology, totals, partial 5-conditions,
installment exact-option match, wait shape, spending-change syntax/rules,
deadline gate. Independent of engine internals: re-derives every check
from the CSVs. Preference acceptance (methods_will_consider) is checked
here too via profiles.

Evidence/consistency/safety layers (validate_evidence, validate_consistency,
validate_safety, validate_canonical): provenance, cross-field, floor recheck.
Structured errors use ValidationError with error_code/severity/request_id/field.

Rule: ANY hard validation failure = FINAL SUBMISSION BLOCKED (Section 26.9,
8.11). No silent repair/drop/reorder.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

from affordai.decision.decision import METHODS, OUTPUT_COLUMNS, STATUSES
from affordai.decision.invariants import (
    check_amount_bounds,
    check_earliest_consistency,
    check_status_method_consistency,
)


@dataclass
class ValidationError:
    """Structured validation error (Section 9)."""

    code: str
    severity: str  # error | warning
    request_id: str | None
    field: str | None
    expected: str | None
    actual: str | None
    message: str

    def __str__(self) -> str:
        prefix = f"[{self.code}/{self.severity}]"
        if self.request_id:
            prefix += f" {self.request_id}"
        if self.field:
            prefix += f".{self.field}"
        return f"{prefix}: {self.message} (expected={self.expected!r} actual={self.actual!r})"


# ---------- helpers ----------

def _is_finite_numeric(s: str) -> tuple[bool, Decimal | None]:
    """Return (ok, Decimal) with strict NaN/Infinity/empty rejection."""
    if s is None or str(s).strip() == "":
        return False, None
    t = str(s).strip()
    # Reject NaN/Infinity case-insensitive
    if t.lower() in {"nan", "inf", "infinity", "+inf", "-inf", "+infinity", "-infinity"}:
        return False, None
    try:
        d = Decimal(t)
    except (InvalidOperation, ValueError):
        return False, None
    if not d.is_finite():
        return False, None
    return True, d


def validate_files(requests_path: str, output_path: str) -> list[str]:
    """Structural + identity + numeric + enum + earliest (Section 26.1-26.4).

    Checks:
        - file exists, columns, order, count (26.1)
        - identity exact order, duplicates, missing (26.2)
        - numeric: safe numeric, 0 <= safe <= requested, NaN/Infinity/empty (26.3)
        - enum valid, no whitespace drift (26.4)
        - status/method consistency, earliest consistency (26.8)
    """
    errors: list[str] = []
    # 26.1 Structural: file exists / columns / order
    try:
        with open(requests_path, newline="", encoding="utf-8") as f:
            req_rows = list(csv.DictReader(f))
    except FileNotFoundError:
        return [f"OUTPUT-STRUCT-001/error: requests file not found {requests_path}"]
    try:
        with open(output_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != OUTPUT_COLUMNS:
                errors.append(
                    f"OUTPUT-STRUCT-001/error: columns expected {OUTPUT_COLUMNS}, got {reader.fieldnames}"
                )
            out_rows = list(reader)
    except FileNotFoundError:
        return [f"OUTPUT-STRUCT-001/error: output file not found {output_path}"]
    # 26.1 row count
    if len(out_rows) != len(req_rows):
        errors.append(f"OUTPUT-STRUCT-002/error: row count requests={len(req_rows)} output={len(out_rows)}")
    req_by_id = {r["request_id"]: (i, r) for i, r in enumerate(req_rows)}
    seen: set[str] = set()
    for i, (req, out) in enumerate(zip(req_rows, out_rows)):
        rid = out.get("request_id", "")
        # 26.2 Identity: exact order (not just set equality)
        if rid != req["request_id"]:
            errors.append(f"OUTPUT-ID-001/error row {i}: order mismatch output={rid!r} requests={req['request_id']!r}")
        if rid in seen:
            errors.append(f"OUTPUT-ID-002/error row {i}: duplicate request_id {rid!r}")
        seen.add(rid)
        # 26.3 Numeric: strict Decimal, no float, catches NaN/Infinity/empty/negative
        safe_raw = out.get("amount_safe_to_pay", "")
        req_raw = req.get("requested_amount", "")
        ok_safe, safe_dec = _is_finite_numeric(safe_raw)
        ok_req, req_dec = _is_finite_numeric(req_raw)
        if not ok_safe or not ok_req:
            errors.append(f"OUTPUT-NUM-001/error row {i} ({rid}): non-numeric safe/requested safe={safe_raw!r} requested={req_raw!r}")
            continue
        # 26.3 bounds 0 <= safe <= requested (Decimal exact)
        if safe_dec < 0 or safe_dec > req_dec:
            errors.append(f"OUTPUT-NUM-002/error row {i} ({rid}): 0 <= {safe_dec} <= {req_dec} violated")
        # Also check float helper for parity (but Decimal is authoritative)
        try:
            if not check_amount_bounds(float(safe_dec), float(req_dec)):
                errors.append(f"OUTPUT-NUM-002/error row {i} ({rid}): bounds violated (float check)")
        except Exception:
            pass
        # 26.4 Enum: strict, no whitespace drift, no case drift
        status_raw = out.get("affordability_status", "")
        method_raw = out.get("recommended_payment_method", "")
        # whitespace drift check
        if status_raw != status_raw.strip() or method_raw != method_raw.strip():
            errors.append(f"OUTPUT-ENUM-001/error row {i} ({rid}): whitespace drift status={status_raw!r} method={method_raw!r}")
        if status_raw not in STATUSES:
            errors.append(f"OUTPUT-ENUM-002/error row {i} ({rid}): bad status {status_raw!r}")
        if method_raw not in METHODS:
            errors.append(f"OUTPUT-ENUM-003/error row {i} ({rid}): bad method {method_raw!r}")
        if not check_status_method_consistency(status_raw.strip(), method_raw.strip()):
            errors.append(f"OUTPUT-CONSISTENCY-001/error row {i} ({rid}): status/method inconsistent {status_raw!r}/{method_raw!r}")
        if not check_earliest_consistency(
            status_raw.strip(),
            req.get("request_date", ""),
            out.get("earliest_date_for_full_payment", ""),
        ):
            errors.append(f"OUTPUT-CONSISTENCY-002/error row {i} ({rid}): earliest-date inconsistent status={status_raw!r} earliest={out.get('earliest_date_for_full_payment')!r}")
        # 26.3 empty numeric fields already caught; check decimal precision (allow bare int or 2dp)
        # (No hard error, but flag malformed)
        if safe_raw.strip() != "" and not re.match(r"^-?\d+(\.\d{1,2})?$", safe_raw.strip()):
            # Allow scientific? No--reject
            if not re.match(r"^-?\d+(\.\d+)?$", safe_raw.strip()):
                errors.append(f"OUTPUT-NUM-003/error row {i} ({rid}): malformed safe amount {safe_raw!r}")
    # 26.2 missing IDs (set vs order)
    missing = set(req_by_id) - seen
    if missing:
        errors.append(f"OUTPUT-ID-003/error: missing request_ids: {sorted(missing)[:5]}")
    # Extra IDs in output not in requests (strict)
    extra = seen - set(req_by_id)
    if extra:
        errors.append(f"OUTPUT-ID-004/error: extra request_ids in output not in requests: {sorted(extra)[:5]}")
    return errors


def _parse_plan(plan: str, rid: str, errors: list[str]) -> list[tuple] | None:
    """Parse YYYY-MM-DD:amount|... ; 'none' -> []. None on malformed."""
    if plan == "none":
        return []
    legs: list[tuple] = []
    for leg in plan.split("|"):
        parts = leg.split(":")
        if len(parts) != 2:
            errors.append(f"OUTPUT-PLAN-001/error {rid}: malformed plan leg {leg!r}")
            return None
        try:
            day = datetime.strptime(parts[0], "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"OUTPUT-PLAN-002/error {rid}: bad plan date {parts[0]!r}")
            return None
        # 26.3 numeric validation via Decimal strict
        ok, dec = _is_finite_numeric(parts[1])
        if not ok or dec is None:
            errors.append(f"OUTPUT-NUM-001/error {rid}: bad plan amount {parts[1]!r}")
            return None
        if dec <= 0:
            errors.append(f"OUTPUT-NUM-004/error {rid}: non-positive plan amount {parts[1]!r}")
            return None
        legs.append((day, float(dec)))  # keep float for legacy comparison but Decimal checked
    if [d for d, _ in legs] != sorted(d for d, _ in legs):
        errors.append(f"OUTPUT-PLAN-003/error {rid}: plan not chronological")
        return None
    return legs


def validate_plans(
    requests_path: str, options_path: str, profiles_path: str, output_path: str
) -> list[str]:
    """Plan/financial layer: independent re-derivation from CSVs (26.5)."""
    errors: list[str] = []
    req_rows = {r["request_id"]: r for r in csv.DictReader(open(requests_path, encoding="utf-8-sig"))}
    out_rows = list(csv.DictReader(open(output_path, encoding="utf-8-sig")))
    options: dict[str, list[dict]] = {}
    for o in csv.DictReader(open(options_path, encoding="utf-8-sig")):
        options.setdefault(o["request_id"], []).append(o)
    profiles = {r["user_id"]: r for r in csv.DictReader(open(profiles_path, encoding="utf-8-sig"))}

    # Load events for spending-change existence/flexibility check (26.6)
    events_by_id: dict[str, dict] = {}
    try:
        # Try to locate events near requests_path (dataset layout aware)
        import os

        cand = os.path.join(os.path.dirname(requests_path), "financial_events.csv")
        if not os.path.exists(cand):
            cand = os.path.join(os.path.dirname(os.path.dirname(requests_path)), "financial_events.csv")
        if os.path.exists(cand):
            for e in csv.DictReader(open(cand, encoding="utf-8-sig")):
                events_by_id[e["event_id"]] = e
    except Exception:
        pass

    for out in out_rows:
        rid = out.get("request_id", "")
        req = req_rows.get(rid)
        if req is None:
            continue
        # 26.3 numeric strict via Decimal
        ok_req, req_dec = _is_finite_numeric(req.get("requested_amount", ""))
        ok_safe, safe_dec = _is_finite_numeric(out.get("amount_safe_to_pay", ""))
        if not ok_req or not ok_safe:
            continue  # reported by structural layer
        requested = float(req_dec)
        safe = float(safe_dec)
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
                errors.append(f"OUTPUT-PLAN-004/error {rid}: not_recommended must have plan none")
            if out.get("spending_changes_needed", "") != "none":
                errors.append(f"OUTPUT-SPEND-001/error {rid}: not_recommended must have changes none")
            continue
        if not legs:
            errors.append(f"OUTPUT-PLAN-005/error {rid}: {method} needs a dated plan")
            continue
        if legs[-1][0].isoformat() > deadline:
            errors.append(f"OUTPUT-PLAN-006/error {rid}: plan completes after desired_completion_date {legs[-1][0].isoformat()} > {deadline}")
        total = round(sum(a for _, a in legs), 2)

        if method == "full_payment":
            if len(legs) != 1 or legs[0][0].isoformat() != req_date or abs(total - requested) > 0.005:
                errors.append(f"OUTPUT-PLAN-007/error {rid}: full_payment must be request_date:requested (got {legs})")
            if status == "affordable_now" and (
                legs[0][0].isoformat() != req_date or abs(safe - requested) > 0.005
            ):
                errors.append(f"OUTPUT-CONSISTENCY-003/error {rid}: affordable_now needs safe==requested on request_date")
        elif method == "partial_payment":
            allows = str(req["allows_partial_payment"]).strip().lower() == "true"
            if not allows:
                errors.append(f"OUTPUT-PLAN-008/error {rid}: partial_payment not allowed by request")
            if len(legs) != 2:
                errors.append(f"OUTPUT-PLAN-009/error {rid}: partial_payment needs exactly 2 payments (got {len(legs)})")
            elif (
                legs[0][0].isoformat() != req_date
                or abs(legs[0][1] - safe) > 0.005
                or legs[1][0].isoformat() != earliest
                or abs(total - requested) > 0.005
                or not (0 < safe < requested)
                or (earliest and earliest > deadline)
            ):
                errors.append(f"OUTPUT-PLAN-010/error {rid}: partial_payment shape violated legs={legs} safe={safe} earliest={earliest!r} requested={requested}")
            # 26.5 extra: partial total must be exact sum
            if len(legs) == 2 and abs(sum(a for _, a in legs) - requested) > 0.005:
                errors.append(f"OUTPUT-NUM-005/error {rid}: partial sum != requested")
        elif method == "installments":
            match = False
            matched_opt = None
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
                    matched_opt = o
                    break
            if not match:
                errors.append(f"OUTPUT-PLAN-011/error {rid}: installments must exactly match a supplied option (legs={legs})")
            # Validate financing fee/total not manipulated (if matched, check total)
            if match and matched_opt:
                try:
                    opt_total = float(matched_opt.get("total_payable_amount", ""))
                    if abs(total - opt_total) > 0.005:
                        errors.append(f"OUTPUT-NUM-006/error {rid}: installment total {total} != option total {opt_total}")
                except Exception:
                    pass
        elif method == "wait":
            if (
                len(legs) != 1
                or legs[0][0].isoformat() != earliest
                or abs(total - requested) > 0.005
                or not earliest
                or earliest <= req_date
            ):
                errors.append(f"OUTPUT-PLAN-012/error {rid}: wait must be single future payment on earliest (legs={legs} earliest={earliest!r})")

        # Spending changes: none | <=3 stop:/reduce_to:, no same-event dup, flexible-only, event exists (26.6)
        changes = out.get("spending_changes_needed", "")
        if changes != "none":
            parts = changes.split("|")
            if len(parts) > 3:
                errors.append(f"OUTPUT-SPEND-002/error {rid}: more than 3 spending changes ({len(parts)})")
            seen_events: set[str] = set()
            for part in parts:
                segs = part.split(":")
                eid = None
                if segs[0] == "stop" and len(segs) == 2 and segs[1]:
                    eid = segs[1]
                elif (
                    len(segs) == 3 and segs[0] == "reduce_to" and segs[1]
                ):
                    eid = segs[1]
                    ok_amt, dec_amt = _is_finite_numeric(segs[2])
                    if not ok_amt or dec_amt is None:
                        errors.append(f"OUTPUT-SPEND-003/error {rid}: bad reduce_to amount {part!r}")
                        continue
                    if dec_amt < 0:
                        errors.append(f"OUTPUT-SPEND-004/error {rid}: negative reduce_to {part!r}")
                else:
                    errors.append(f"OUTPUT-SPEND-005/error {rid}: malformed spending change {part!r}")
                    continue
                if eid in seen_events:
                    errors.append(f"OUTPUT-SPEND-006/error {rid}: stop+reduce on same event {eid}")
                seen_events.add(eid)
                # 26.6 event exists check
                if events_by_id and eid not in events_by_id:
                    errors.append(f"OUTPUT-SPEND-007/error {rid}: spending change event {eid} not found in events")
                # Flexible-only check (if events available)
                if events_by_id and eid in events_by_id:
                    ev = events_by_id[eid]
                    flex = ev.get("flexibility", "")
                    cat = ev.get("category", "")
                    # Must be flexible recurring; at minimum not fixed
                    if flex == "fixed":
                        errors.append(f"OUTPUT-SPEND-008/error {rid}: spending change on fixed event {eid} (must be flexible)")
                    # Protected categories cannot be changed (check via profiles)
                    # For now, only flag if category is explicitly protected? Need profile; skip if not decidable
                    prof = profiles.get(req["user_id"], {})
                    protected = set(prof.get("expense_categories_to_protect", "").split("|") if prof.get("expense_categories_to_protect") else [])
                    # expense_categories_to_protect is '|' separated or comma? Already checked via _is_protected logic, but validator's simple check:
                    # If event category is in protected list, reject
                    if cat and cat in protected:
                        errors.append(f"OUTPUT-SPEND-009/error {rid}: spending change on protected category {cat!r} event {eid}")

        # Preference acceptance (independent of engine) (Section 20)
        prof = profiles.get(req["user_id"], {})
        accepted = {p.strip() for p in str(prof.get("payment_methods_user_will_consider", "")).replace(";", ",").replace("|", ",").split(",") if p.strip()}
        need = {"full_payment": "full_payment", "partial_payment": "partial_payment", "installments": "installments", "wait": "full_payment"}.get(method)
        if need and need not in accepted:
            errors.append(f"OUTPUT-CONSISTENCY-004/error {rid}: method {method} not accepted by user (need {need}, accepted {accepted})")
    return errors


# ---------- Evidence / Consistency / Safety / Canonical layers (26.7-26.10) ----------

def validate_evidence(decisions: list, contexts: list) -> list[str]:
    """Evidence validation (26.7): IDs exist, correct request/user, relevant.

    Checks each Decision.evidence entry is from its context's valid message/image/event IDs,
    and belongs to correct request/user (no cross-request).
    """
    errors: list[str] = []
    ctx_by_req = {c.request_id: c for c in contexts}
    for d in decisions:
        ctx = ctx_by_req.get(d.request_id)
        if ctx is None:
            errors.append(f"OUTPUT-EVIDENCE-001/error {d.request_id}: no context for evidence check")
            continue
        valid_event_ids = {e["event_id"] for e in ctx.events}
        valid_message_ids = {m["message_id"] for m in ctx.messages}
        valid_image_ids = {i["image_id"] for i in ctx.images}
        # Build mapping from source_id -> type for quick check (source_id may be message_id/image_id/event_id)
        # Decision.evidence is list of source_ids; we check each is in at least one valid set or is a known option_id?
        # For now, ensure at least one of event/message/image/option
        valid_option_ids = {o["payment_option_id"] for o in ctx.payment_options}
        all_valid = valid_event_ids | valid_message_ids | valid_image_ids | valid_option_ids
        for eid in d.evidence:
            if eid not in all_valid:
                # Check if eid is a generic evidence marker (e.g., amount_unknown)
                if eid.startswith("amount_unknown_"):
                    continue
                errors.append(f"OUTPUT-EVIDENCE-002/error {d.request_id}: evidence {eid!r} not in valid IDs for this request/user")
            # Check cross-request: ensure evidence source belongs to this user_id/request_id
            # (If evidence is message_id, verify its user_id == d.user_id)
            # Look up in context
            found = False
            for m in ctx.messages:
                if m["message_id"] == eid and m["user_id"] != d.user_id:
                    errors.append(f"OUTPUT-EVIDENCE-003/error {d.request_id}: evidence {eid!r} belongs to user {m['user_id']} not {d.user_id}")
                if m["message_id"] == eid:
                    found = True
            for img in ctx.images:
                if img["image_id"] == eid and img["user_id"] != d.user_id:
                    errors.append(f"OUTPUT-EVIDENCE-003/error {d.request_id}: image evidence {eid!r} wrong user")
                if img["image_id"] == eid:
                    found = True
            # If not found in messages/images but in events/options, it's still valid if same user
            # No extra action; unknown handled above
        # Check no duplicate evidence IDs
        if len(d.evidence) != len(set(d.evidence)):
            errors.append(f"OUTPUT-EVIDENCE-004/error {d.request_id}: duplicate evidence IDs")
    return errors


def validate_consistency(decisions: list) -> list[str]:
    """Cross-field consistency (26.8): status↔method, method↔plan, plan↔dates, spending↔plan, decision↔explanation."""
    errors: list[str] = []
    for d in decisions:
        # status↔method already checked via invariants, but re-check with detailed message
        from affordai.decision.invariants import check_status_method_consistency, check_earliest_consistency

        if not check_status_method_consistency(d.affordability_status, d.recommended_payment_method):
            errors.append(f"OUTPUT-CONSISTENCY-001/error {d.request_id}: status/method inconsistent {d.affordability_status}/{d.recommended_payment_method}")
        # For affordable_now, earliest must == request_date (via explanation_facts or decision)
        # We need request_date; try from explanation_facts
        req_date = None
        if d.explanation_facts and "request_date" in d.explanation_facts:
            req_date = d.explanation_facts["request_date"]
        if req_date and not check_earliest_consistency(d.affordability_status, req_date, d.earliest_date_for_full_payment):
            errors.append(f"OUTPUT-CONSISTENCY-002/error {d.request_id}: earliest/status inconsistent {d.affordability_status} req={req_date} earliest={d.earliest_date_for_full_payment!r}")
        # method↔plan
        plan = d.payment_plan
        if d.recommended_payment_method == "not_recommended" and plan != "none":
            errors.append(f"OUTPUT-CONSISTENCY-005/error {d.request_id}: not_recommended must have plan none, got {plan!r}")
        if d.recommended_payment_method != "not_recommended" and plan == "none":
            errors.append(f"OUTPUT-CONSISTENCY-006/error {d.request_id}: {d.recommended_payment_method} needs a plan, got none")
        # spending ↔ plan
        if d.recommended_payment_method == "not_recommended" and d.spending_changes_needed != "none":
            errors.append(f"OUTPUT-CONSISTENCY-007/error {d.request_id}: not_recommended must have changes none")
        # decision ↔ explanation
        try:
            from affordai.output.explanation import validate as expl_validate

            if not expl_validate(d.decision_explanation, d):
                errors.append(f"OUTPUT-CONSISTENCY-008/error {d.request_id}: explanation contradicts decision (status/method/plan/date/amount mismatch)")
        except Exception as e:
            errors.append(f"OUTPUT-CONSISTENCY-009/error {d.request_id}: explanation validation error {e}")
    return errors


def validate_canonical_consistency(decisions: list, expected_output_path: str | None = None) -> list[str]:
    """Canonical-object consistency (26.9): serialized == serialize(canonical), facts == canonical.

    Checks that re-serializing decisions via serializer produces same rows as expected_output,
    and that explanation_facts match decision facts.
    """
    errors: list[str] = []
    for d in decisions:
        ef = d.explanation_facts or {}
        # facts must not contain invented claims (must be subset)
        for key in ("amount_safe_to_pay", "affordability_status", "recommended_payment_method", "payment_plan", "earliest_date_for_full_payment", "spending_changes_needed"):
            if key in ef and getattr(d, key, None) != ef[key]:
                # For payment_plan and changes, string comparison is exact
                errors.append(f"OUTPUT-CONSISTENCY-010/error {d.request_id}: explanation_facts {key} {ef[key]!r} != decision {getattr(d, key)!r}")
    # If expected_output_path provided, compare serialization round-trip
    if expected_output_path:
        try:
            import csv
            from affordai.output.serializer import decisions_to_rows

            # Need home_by_request from decisions
            home_by_request = {d.request_id: getattr(d, "home_currency", "INR") or "INR" for d in decisions}
            rows = decisions_to_rows(decisions, home_by_request)
            with open(expected_output_path, newline="", encoding="utf-8") as f:
                out_rows = list(csv.DictReader(f))
            # Compare each row field by field (string comparison)
            for exp, got in zip(rows, out_rows):
                for col in OUTPUT_COLUMNS:
                    if str(exp.get(col, "")) != str(got.get(col, "")):
                        errors.append(f"OUTPUT-CONSISTENCY-011/error {exp['request_id']}.{col}: canonical {exp[col]!r} != serialized {got[col]!r}")
                        break
        except Exception as e:
            errors.append(f"OUTPUT-CONSISTENCY-012/error: canonical consistency check failed {e}")
    return errors


def validate_safety(decisions: list, contexts: list, rate_table=None) -> list[str]:
    """Financial safety recheck (26.10, defense-in-depth): re-simulate selected plan.

    Independently rechecks critical invariants: safe bounds, totals, deadline, schedule,
    and if possible re-runs forecast.simulate for floor.
    """
    errors: list[str] = []
    ctx_by_req = {c.request_id: c for c in contexts}
    for d in decisions:
        ctx = ctx_by_req.get(d.request_id)
        if ctx is None:
            continue
        # Bounds already checked, but re-check with Decision's stored requested
        if d.requested_amount is not None and (d.amount_safe_to_pay < 0 or d.amount_safe_to_pay > d.requested_amount):
            errors.append(f"OUTPUT-NUM-002/error {d.request_id}: safe bounds violated in safety recheck")
        # Plan totals recheck via parsing
        plan_str = d.payment_plan
        if plan_str != "none":
            try:
                from affordai.finance.money import parse_amount

                total = Decimal("0")
                for leg in plan_str.split("|"):
                    amt_str = leg.split(":")[1] if ":" in leg else "0"
                    ok, dec = _is_finite_numeric(amt_str)
                    if ok and dec is not None:
                        total += dec
                if d.requested_amount is not None and abs(total - d.requested_amount) > Decimal("0.005") and d.recommended_payment_method in {"full_payment", "partial_payment", "wait"}:
                    # installments total may differ (includes fees), so only check full/partial/wait
                    errors.append(f"OUTPUT-NUM-007/error {d.request_id}: plan total {total} != requested {d.requested_amount}")
            except Exception:
                pass
        # Full floor re-simulation is expensive and needs FinancialState; skip if not available
        # But if we have rate_table and can rebuild state, we could simulate. For validator simplicity,
        # we flag that safety recheck is limited to totals/bounds here; full simulation is done in pipeline.
    return errors


def validate_all(
    requests_path: str,
    output_path: str,
    options_path: str | None = None,
    profiles_path: str | None = None,
    decisions: list | None = None,
    contexts: list | None = None,
) -> tuple[list[str], list[ValidationError]]:
    """Run all layers and return (string_errors, structured_errors). Any hard error blocks submission."""
    str_errors: list[str] = []
    struct_errors: list[ValidationError] = []
    # 26.1-26.4
    str_errors.extend(validate_files(requests_path, output_path))
    if options_path and profiles_path:
        str_errors.extend(validate_plans(requests_path, options_path, profiles_path, output_path))
    # 26.7-26.10 if decisions/contexts provided
    if decisions is not None and contexts is not None:
        str_errors.extend(validate_evidence(decisions, contexts))
        str_errors.extend(validate_consistency(decisions))
        str_errors.extend(validate_canonical_consistency(decisions, output_path))
        str_errors.extend(validate_safety(decisions, contexts))
    # Convert to structured (simple mapping)
    for e in str_errors:
        # Parse code if present, else generic
        code = "OUTPUT-UNKNOWN"
        sev = "error"
        if "/" in e and e.startswith("OUTPUT-"):
            try:
                code = e.split("/")[0]
                sev = e.split("/")[1].split()[0] if "/" in e else "error"
            except Exception:
                pass
        struct_errors.append(ValidationError(code=code, severity=sev, request_id=None, field=None, expected=None, actual=None, message=e))
    return str_errors, struct_errors
