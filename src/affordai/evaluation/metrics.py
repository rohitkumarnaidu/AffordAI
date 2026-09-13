from __future__ import annotations

"""Local-proxy metrics vs sample_requests.csv (NOT official score)."""

OFFICIAL_SCORE_NOTE = (
    "OFFICIAL HackerRank score: UNKNOWN (no official formula published). "
    "Every metric below is a LOCAL PROXY / LOCAL MEASUREMENT unless tagged otherwise."
)

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
        "provenance": "LOCAL PROXY -- sample_requests.csv are illustrative format "
        "examples, NOT official eval labels. OFFICIAL score: UNKNOWN.",
    }


# ---------------------------------------------------------------------------
# Section 27.2 -- required metric definitions (each reproducible).
# Fields: definition, numerator, denominator, pass/fail, official-or-local,
# expected-truth source. No vague scores.
# ---------------------------------------------------------------------------
METRIC_DEFS: dict[str, dict[str, str]] = {
    "structural_validity": {
        "definition": "output.csv has exact 8 columns in order, 250 rows + header, "
        "unique request_ids matching requests.csv in input order",
        "numerator": "1 if validate_files(requests, output) == [] else 0",
        "denominator": "1 evaluation run",
        "pass_fail": "PASS iff numerator == 1",
        "official_or_local": "LOCAL (structural gate; official hidden checks UNKNOWN)",
        "truth_source": "dataset/official/requests.csv + decision.OUTPUT_COLUMNS",
    },
    "numerical_correctness": {
        "definition": "0 <= amount_safe_to_pay <= requested_amount for every row; "
        "plan legs sum to required totals; safe MAE vs sample rows reported only",
        "numerator": "rows satisfying bounds + plan arithmetic",
        "denominator": "all output rows",
        "pass_fail": "PASS iff numerator == denominator",
        "official_or_local": "LOCAL PROXY (bounds exact per Tier-1; sample MAE illustrative only)",
        "truth_source": "requests.csv requested_amount + validator plan re-derivation",
    },
    "decision_correctness": {
        "definition": "status/method match on the 25 sample rows (format examples); "
        "status<->method consistency on all 250 rows",
        "numerator": "sample status+method matches; consistent rows",
        "denominator": "25 samples; 250 production rows",
        "pass_fail": "sample accuracy reported (no threshold claimed); "
        "consistency must be 250/250",
        "official_or_local": "LOCAL PROXY -- samples are NOT eval labels; OFFICIAL: UNKNOWN",
        "truth_source": "sample_requests.csv (illustrative) + decision-matrix allowed pairs",
    },
    "plan_correctness": {
        "definition": "validate_plans() errors == 0: chronological legs, exact "
        "installment option match, partial 2-payment shape, deadline respected",
        "numerator": "1 if validate_plans(...) == [] else 0",
        "denominator": "1 evaluation run",
        "pass_fail": "PASS iff numerator == 1",
        "official_or_local": "LOCAL (re-derives schedules from request_payment_options.csv)",
        "truth_source": "request_payment_options.csv + financial_profiles (deadlines)",
    },
    "evidence_validity": {
        "definition": "validate_evidence() errors == 0: every cited id exists and "
        "belongs to the same request/user",
        "numerator": "1 if validate_evidence(decisions, contexts) == [] else 0",
        "denominator": "1 evaluation run",
        "pass_fail": "PASS iff numerator == 1",
        "official_or_local": "LOCAL",
        "truth_source": "messages.csv / images.csv / financial_events.csv ids + ownership",
    },
    "explanation_consistency": {
        "definition": "explanation.validate(text, decision) true for every row; "
        "no invented amounts/dates/evidence, no decision contradiction",
        "numerator": "decisions with valid explanations",
        "denominator": "all decisions",
        "pass_fail": "PASS iff numerator == denominator",
        "official_or_local": "LOCAL",
        "truth_source": "canonical Decision facts (decision.py) + explanation_mod.validate",
    },
    "robustness": {
        "definition": "regression + adversarial suites green; per-request fallback "
        "never crashes batch (fallbacks counted, rows still valid)",
        "numerator": "passing regression/adversarial tests; valid fallback rows",
        "denominator": "total regression/adversarial tests; total requests",
        "pass_fail": "PASS iff suites green and output validator green",
        "official_or_local": "LOCAL robustness measurement",
        "truth_source": "tests/regression + tests/adversarial + pipeline fallback counter",
    },
    "token_usage": {
        "definition": "model calls, input/output/total tokens, avg per request "
        "for the FINAL full-dataset run",
        "numerator": "metered counts (0 on deterministic path)",
        "denominator": "n_requests for averages",
        "pass_fail": "informational; optimization valid only at equal accuracy",
        "official_or_local": "LOCAL measurement",
        "truth_source": "UsageReport from pipeline run()",
    },
    "cost": {
        "definition": "estimated total + per-request cost for the FINAL run, "
        "per-model + overall",
        "numerator": "metered estimate (0.00 with no model calls)",
        "denominator": "n_requests for per-request",
        "pass_fail": "informational",
        "official_or_local": "LOCAL estimate",
        "truth_source": "evaluation/usage_report.md (final metered run)",
    },
}

FAILURE_CATEGORIES = [
    "structural", "identity", "numeric", "date", "decision", "payment",
    "evidence", "explanation", "adversarial", "regression", "runtime",
    "token_cost",
]


def full_dataset_metrics(
    decisions: list,
    contexts: list,
    dataset_dir: str = "dataset/official",
    output_path: str = "output.csv",
) -> dict:
    """Compute all Section 27.2 metrics on the full production dataset."""
    from affordai.output import explanation as explanation_mod
    from affordai.output.validator import (
        validate_consistency,
        validate_evidence,
        validate_files,
        validate_plans,
    )

    req = f"{dataset_dir}/requests.csv"
    opt = f"{dataset_dir}/request_payment_options.csv"
    prof = f"{dataset_dir}/financial_profiles.csv"
    structural_errors = validate_files(req, output_path)
    plan_errors = validate_plans(req, opt, prof, output_path)
    ev_errors = validate_evidence(decisions, contexts)
    cons_errors = validate_consistency(decisions)
    n = len(decisions)
    expl_bad: list[str] = []
    for d in decisions:
        try:
            ok = bool(explanation_mod.validate(d.decision_explanation, d))
        except Exception:
            ok = False
        if not ok:
            expl_bad.append(d.request_id)
    bounds_bad = [
        d.request_id
        for d in decisions
        if not (
            d.requested_amount is not None
            and 0 <= d.amount_safe_to_pay <= d.requested_amount
        )
    ]
    return {
        "n_requests": n,
        "structural_validity": {"errors": len(structural_errors), "pass": not structural_errors},
        "numerical_correctness": {"bounds_violations": bounds_bad, "pass": not bounds_bad},
        "plan_correctness": {"errors": len(plan_errors), "pass": not plan_errors},
        "evidence_validity": {"errors": len(ev_errors), "pass": not ev_errors},
        "explanation_consistency": {
            "invalid_ids": expl_bad,
            "rate": ((n - len(expl_bad)) / n) if n else 0.0,
            "pass": not expl_bad,
        },
        "decision_consistency": {"errors": len(cons_errors), "pass": not cons_errors},
        "structural_errors_sample": structural_errors[:5],
        "plan_errors_sample": plan_errors[:5],
        "evidence_errors_sample": ev_errors[:5],
        "consistency_errors_sample": cons_errors[:5],
        "provenance": "LOCAL MEASUREMENT on full participant-facing dataset; "
        "OFFICIAL hidden evaluation: UNKNOWN",
    }


def categorize_errors(full_metrics: dict) -> dict[str, int]:
    """Map metric failures to Section 27.4 failure categories."""
    cats: dict[str, int] = {c: 0 for c in FAILURE_CATEGORIES}
    if not full_metrics["structural_validity"]["pass"]:
        cats["structural"] += full_metrics["structural_validity"]["errors"]
        cats["identity"] += full_metrics["structural_validity"]["errors"]
    if not full_metrics["numerical_correctness"]["pass"]:
        cats["numeric"] += len(full_metrics["numerical_correctness"]["bounds_violations"])
    if not full_metrics["plan_correctness"]["pass"]:
        cats["payment"] += full_metrics["plan_correctness"]["errors"]
    if not full_metrics["evidence_validity"]["pass"]:
        cats["evidence"] += full_metrics["evidence_validity"]["errors"]
    if not full_metrics["explanation_consistency"]["pass"]:
        cats["explanation"] += len(full_metrics["explanation_consistency"]["invalid_ids"])
    if not full_metrics["decision_consistency"]["pass"]:
        cats["decision"] += full_metrics["decision_consistency"]["errors"]
    return cats
