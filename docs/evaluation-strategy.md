# Evaluation Strategy (LOCAL PROXY — NOT Official HackerRank Score)

> **OFFICIAL HackerRank score:** UNKNOWN (no published formula). All numbers below are
> **LOCAL MEASUREMENT / LOCAL PROXY** unless labelled otherwise (see `evaluation/README.md`).
> Forbidden claim: “local score = official score”.

## Table of Contents

- [27.1 Official vs Local](#271-official-vs-local)
- [27.2 Metrics](#272-metrics-reproducible-definitions-in-srcaffordaiuevaluationmetrics pymetric_defs)
- [27.3 Evaluation Sets](#273-evaluation-sets-declared-in-evaluationdatasetsjson)
- [27.4 Reporting](#274-reporting-scriptseval_reportpy)
- [28 Ablation](#28-ablation-scriptsrun_ablationpy----reproducible-e0-e7)
- [29 Regression](#29-regression-testsregression)
- [30 Adversarial](#30-adversarial-testsadversarialtest_sections_27_30_threatspy--docsthreat-modelmd)
- [Measured Baseline](#measured-baseline-2026-09-13-250-rows)

## 27.1 Official vs Local

- OFFICIAL: hidden evaluation, unknown formula -- never claimed.
- LOCAL: harness, reconstructed expected outputs, proxy metrics, synthetic results,
  robustness/token measurements via src/affordai/evaluation/*.
- Vocabulary enforced in evaluation/README.md (OFFICIAL / LOCAL MEASUREMENT / LOCAL PROXY / INFERENCE / UNKNOWN).

## 27.2 Metrics (reproducible definitions in src/affordai/evaluation/metrics.py::METRIC_DEFS)

Each metric defines: definition, numerator, denominator, pass/fail, official-or-local, truth source.

1. structural_validity -- 8 cols order, 250 rows + header, unique ordered ids (truth: OUTPUT_COLUMNS + requests.csv)
2. numerical_correctness -- 0 <= safe <= requested + plan leg sums (truth: requested_amount + re-derived plans)
3. decision_correctness -- sample status/method (LOCAL PROXY vs 25 sample rows, NOT eval labels) + status<->method consistency on 250 rows
4. plan_correctness -- validate_plans 0 errors (chronological, exact installment, partial 2-leg, deadline)
5. evidence_validity -- validate_evidence 0 errors (ids exist + belong to request/user)
6. explanation_consistency -- explanation.validate true for every row (no invented amounts/dates)
7. robustness -- regression + adversarial suites green + per-request fallback count
8. token_usage -- provider/model/calls/in/out/total/avg per request (metered FINAL run)
9. cost -- estimated total + per-request, per-model + overall (from evaluation/usage_report.md)
+ runtime, failure count/category, per-request and per-category results, regression status (captured in evaluation/reports/eval_*.json).

No vague scores (e.g. "quality=87") without definition.

## 27.3 Evaluation Sets (declared in evaluation/datasets/*.json)

- A. 25 solved samples -- dataset/official/sample_requests.csv (LOCAL PROXY, illustrative format examples)
- B. Hand-built edge cases -- tests/edge_cases/* (deterministic boundaries)
- C. Adversarial cases -- tests/adversarial/* (Section 30 threat cases, 29 cases)
- D. Regression cases -- tests/regression/* + tests/regression/REGRESSIONS.md (every historical bug, 15 groups)
- E. Full dataset -- 250 requests.csv rows through production pipeline + validator + harness + suites

Each case carries: case ID, input ref, expected, expected provenance, actual, pass/fail, failure category, diagnostics (captured in eval json + test names).

## 27.4 Reporting (scripts/eval_report.py)

Generates machine-readable (eval_*.json) + human-readable (eval_*.md) reports:

- BASELINE: dataset, version, timestamp, test count, metrics, failures
- FINAL: same + deltas
- FAILURE CATEGORIES: structural, identity, numeric, date, decision, payment, evidence, explanation, adversarial, regression, runtime, token/cost (see src/affordai/evaluation/metrics.py::FAILURE_CATEGORIES)
- IMPROVEMENT DELTAS: final - baseline per metric (honest; regressions reported never hidden)
- REMAINING FAILURES: case ID, category, expected, actual, root cause, severity, status (empty when all green; currently all green on full dataset)

Artifacts: evaluation/reports/eval_baseline.{json,md}, eval_final.{json,md}.

## 28 Ablation (scripts/run_ablation.py -- reproducible E0-E7)

- E0 deterministic baseline (no messages/images)
- E1 E0 + deterministic message interpretation
- E2 E1 + image linkage (UNKNOWN-safe; blank != 0)
- E3 E2 + semantic conflict handling (instrumented: conflict subsets)
- E4 E3 + plan optimization ranking (instrumented: naive-first vs ranked + tie-break units)
- E5 E4 + grounded explanation (instrumented: 100% consistency audit)
- E6 E5 + comprehensive validation (instrumented: negative controls)
- E7 E6 + token optimization accounting: E0 config 0 calls / 0 tokens at equal
  accuracy; metered config (`.env` groq, no vendored SDK) 77 calls / 7864
  estimated input tokens / 0 facts added / decisions byte-identical (replay hash
  `d8386548517835c9`). Tokens are accounting only and never enter decisions.

Comparison tables (required): Version | Decision Accuracy | Plan Accuracy | Evidence | Invalid Outputs | Tokens | Cost | Runtime  +  Component | Benefit | Cost | New Failures | Decision (KEEP/REMOVE). Results in evaluation/reports/ablation_results.{json,md}. Rule: keep only when measurable value justifies complexity.

## 29 Regression (tests/regression/*)

Lifecycle: FAILURE -> capture -> expected -> actual -> root cause -> general rule -> fix -> regression test -> nearby-case test -> full suite -> report. Registry: tests/regression/REGRESSIONS.md. Required groups: row order, wrong decision, wrong payment, wrong date, currency, evidence mismatch, image extraction, cancellation, amendment, duplicate event, preference, partial payment, installments, deadline, minimum balance (each covered in tests/regression/test_sections_27_30_regression.py among other suites).

## 30 Adversarial (tests/adversarial/test_sections_27_30_threats.py + docs/threat-model.md)

Threat model treats messages/images as UNTRUSTED EVIDENCE that never overrides system contract, 90-day safety, payment/ranking rules. Prompt injection is data, not instructions. Five categories, 29 cases: financial (7), temporal (5), data (5), evidence (6), payment (6) with exact boundary values.

## Measured Baseline (2026-09-13, 250 rows)

- structural 0 errors, numerical 0 violations, plan 0 errors, evidence 0, explanation 250/250, decision 0, fallbacks 0, runtime ~2.4s, validator PASS, double-run replay identical (production_hash 620bff42124b0c3d, output sha256 `d8386548517835c9`), clean-room PASS.
- Two metered truths (LOCAL MEASUREMENT, same decisions): E0 config (`LLM_ENABLED != 1`) 0 calls / 0 tokens / cost 0.0000; metered config (`.env` groq `qwen/qwen3.6-27b` + `groq/compound` vision) 77 calls (66 message + 11 image) / 7864 estimated input tokens / 0 output / cost UNKNOWN (no verified `PRICING`) / 0 facts added (`no-backend` fallback, no SDK vendored). `evaluation/usage_report.md` always reflects the FINAL `build_output.py` run, whichever mode it ran in.
- Sample calibration (25 rows, NOT eval labels): status 0.44 / method 0.48 / earliest-exact 0.36 -- used for shape diagnostics only (exposed Tier-1 earliest rule, pipe-split, payroll refs).
