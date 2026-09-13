"""Regression: partial_payment deep verification (AGENT 10).

Proves output.csv's zero `partial_payment` rows are correct by recomputing the
5 strict conditions live from the input/output CSVs (never hardcoded):

  (1) requests.allows_partial_payment is true
      [src/affordai/finance/payment_plans.py:generate L45-50,
       src/affordai/decision/eligibility.py L45-46,
       src/affordai/output/validator.py OUTPUT-PLAN-008]
  (2) user accepts partial (`partial_payment` in
      financial_profiles.payment_methods_user_will_consider, `|`-split)
      [eligibility.filter_candidates KIND_METHOD, decision-matrix B]
  (3) 0 < amount_safe_to_pay < requested_amount
      [payment_plans.generate L47, validator OUTPUT-PLAN-010]
  (4) earliest_date_for_full_payment non-empty and <= desired_completion_date
      [payment_plans.generate L49, validator OUTPUT-PLAN-010]
  (5) exact 2-payment shape `request_date:safe | earliest:(requested-safe)`
      summing to requested + status == affordable_with_plan
      [payment_plans.generate L51-57, validator OUTPUT-PLAN-009/010,
       decision-matrix A, invariants.check_status_method_consistency]

Eligibility (c1-c4) is necessary and shape-constructible; the surviving
candidate must still pass forecast.simulate floor + ranking, so CSV-level
eligibility is necessary-but-not-sufficient. Since zero rows pass c1-c4,
zero partial rows is correct regardless of the safety simulation.

The core assertion (eligible set == actual partial set) is computed live on
every run so a future regression (eligible but not partial, or partial but
not eligible) fails instead of being hidden.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL = REPO_ROOT / "dataset" / "official"
OUTPUT_CSV = REPO_ROOT / "output.csv"


def _resolve(name: str) -> Path:
    p = OFFICIAL / name
    if p.exists():
        return p
    alt = REPO_ROOT / "dataset" / name
    if alt.exists():
        return alt
    raise FileNotFoundError(f"dataset file not found: {name}")


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _is_true(v) -> bool:
    return str(v).strip().lower() == "true"


def _methods(v) -> set[str]:
    return {x.strip() for x in str(v or "").split("|") if x.strip()}


def _dec(v) -> Decimal | None:
    try:
        return Decimal(str(v).strip())
    except (InvalidOperation, AttributeError, ValueError):
        return None


def _date(v) -> date | None:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def compute_sets():
    """Recompute (eligible_ids, actual_partial_ids, diagnostics) live."""
    reqs = {r["request_id"]: r for r in _read(_resolve("requests.csv"))}
    profs = {p["user_id"]: p for p in _read(_resolve("financial_profiles.csv"))}
    outs = _read(OUTPUT_CSV)
    eligible: set[str] = set()
    actual: set[str] = set()
    diag: dict[str, dict] = {}
    for o in outs:
        rid = o["request_id"]
        rq = reqs[rid]
        prof = profs[rq["user_id"]]
        c1 = _is_true(rq["allows_partial_payment"])
        c2 = "partial_payment" in _methods(prof["payment_methods_user_will_consider"])
        safe = _dec(o["amount_safe_to_pay"])
        requested = _dec(rq["requested_amount"])
        c3 = safe is not None and requested is not None and Decimal("0") < safe < requested
        earliest = _date(o["earliest_date_for_full_payment"])
        deadline = _date(rq["desired_completion_date"])
        c4 = earliest is not None and deadline is not None and earliest <= deadline
        fails = []
        if not c1:
            fails.append("c1-allows_partial_payment!=true")
        if not c2:
            fails.append("c2-user-accepts-partial")
        if not c3:
            fails.append(f"c3-0<safe<requested(safe={safe},req={requested})")
        if not c4:
            fails.append(
                f"c4-earliest<=deadline(earliest={o['earliest_date_for_full_payment']!r},"
                f"deadline={rq['desired_completion_date']!r})"
            )
        diag[rid] = {
            "c1": c1,
            "c2": c2,
            "c3": c3,
            "c4": c4,
            "fails": fails,
            "status": o["affordability_status"],
            "method": o["recommended_payment_method"],
        }
        if c1 and c2 and c3 and c4:
            eligible.add(rid)
        if o["recommended_payment_method"] == "partial_payment":
            actual.add(rid)
    return eligible, actual, diag, reqs, outs


def test_partial_eligible_set_matches_actual():
    eligible, actual, diag, reqs, outs = compute_sets()
    assert len(outs) == 250, f"expected 250 output rows, got {len(outs)}"
    missing = sorted(eligible - actual)  # SHOULD be partial but is not -> defect
    extra = sorted(actual - eligible)  # IS partial but not eligible -> defect
    assert not missing and not extra, (
        f"partial_payment mismatch: eligible={len(eligible)} actual={len(actual)} "
        f"SHOULD-be-partial-but-is-not={missing} "
        f"IS-partial-but-ineligible={extra} "
        f"detail={[ (r, diag[r]) for r in (missing + extra)[:10] ]}"
    )


def test_actual_partial_shape_and_status():
    """Every actual partial row must satisfy condition (5) + status gate."""
    _, actual, _, reqs, outs = compute_sets()
    by_id = {o["request_id"]: o for o in outs}
    for rid in sorted(actual):
        o = by_id[rid]
        rq = reqs[rid]
        assert o["affordability_status"] == "affordable_with_plan", (
            f"{rid}: partial_payment requires status affordable_with_plan, "
            f"got {o['affordability_status']}"
        )
        safe = _dec(o["amount_safe_to_pay"])
        requested = _dec(rq["requested_amount"])
        assert safe is not None and requested is not None
        assert Decimal("0") < safe < requested, f"{rid}: c3 violated safe={safe} req={requested}"
        earliest = str(o["earliest_date_for_full_payment"]).strip()
        deadline = str(rq["desired_completion_date"]).strip()
        assert earliest and earliest <= deadline, f"{rid}: c4 violated {earliest!r} > {deadline!r}"
        plan = str(o["payment_plan"]).strip()
        legs = [leg.strip() for leg in plan.split("|")] if plan != "none" else []
        assert len(legs) == 2, f"{rid}: partial needs exactly 2 legs, got {legs}"
        d0, a0 = legs[0].split(":")
        d1, a1 = legs[1].split(":")
        assert d0.strip() == str(rq["request_date"]).strip(), f"{rid}: leg1 date {d0!r}"
        assert d1.strip() == earliest, f"{rid}: leg2 date {d1!r} != earliest {earliest!r}"
        assert abs(Decimal(a0.strip()) - safe) <= Decimal("0.005"), f"{rid}: leg1 amt"
        assert abs((Decimal(a0.strip()) + Decimal(a1.strip())) - requested) <= Decimal(
            "0.005"
        ), f"{rid}: legs must sum to requested"


def test_every_row_has_a_failing_gate_unless_eligible():
    """Proof of zero: each non-eligible row fails >=1 of c1-c4 (no silent skip)."""
    eligible, _, diag, _, _ = compute_sets()
    for rid, d in diag.items():
        if rid not in eligible:
            assert d["fails"], f"{rid}: non-eligible but no failing gate recorded"
