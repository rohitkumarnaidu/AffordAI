# Evaluation -- Official vs Local (Section 27.1)

> **OFFICIAL HackerRank scoring, hidden evaluation, leaderboard result, and any
> official score formula: UNKNOWN** -- no official formula has been published in
> participant-facing sources. Nothing in `evaluation/` claims to BE the official score.

## Vocabulary (mandatory)

| Term | Meaning |
|---|---|
| OFFICIAL | HackerRank hidden evaluation. Always UNKNOWN unless an official source proves otherwise. |
| LOCAL MEASUREMENT | A number this repo actually computed and can reproduce. |
| LOCAL PROXY | A locally reconstructed stand-in (e.g. accuracy vs sample_requests.csv, whose rows are illustrative format examples, NOT eval labels). Never equivalent to OFFICIAL. |
| INFERENCE | A conclusion drawn from evidence, labelled as such. |
| UNKNOWN | Cannot be verified from available sources. |

Forbidden claim: "our local score = HackerRank score". No such equivalence is documented.

## Layout

```
evaluation/
|-- README.md            # this file (27.1 distinction)
|-- datasets/            # 27.3 evaluation sets (manifests + provenance)
|   |-- solved_samples.json
|   |-- edge_cases.json
|   |-- adversarial.json
|   +-- regression.json
|-- reports/             # 27.4 machine + human readable reports
|   |-- eval_baseline.{json,md}
|   |-- eval_final.{json,md}
|   +-- ablation_results.{json,md}
|-- local/               # gitignored scratch (never committed)
+-- usage_report.md      # FINAL full-dataset token/cost (metered)
```

## Metrics (27.2)

Precise definitions live in src/affordai/evaluation/metrics.py::METRIC_DEFS
(one entry per metric: definition, numerator, denominator, pass/fail,
official-or-local, truth source): structural validity, numerical correctness,
decision correctness, plan correctness, evidence validity, explanation
consistency, robustness, token usage, cost (+ runtime, failure counts,
per-request/per-category results, regression status in reports).

## Sets (27.3)

- A. 25 solved samples -- dataset/official/sample_requests.csv. Provenance: LOCALLY reconstructed comparison; rows are format/decision-style examples, NOT eval labels (see docs/evaluation-strategy.md). Used for shape/calibration diagnostics only.
- B. Hand-built edge cases -- tests/edge_cases/ (deterministic boundary tests).
- C. Adversarial cases -- Section 30 suites in tests/adversarial/ (+ manifest datasets/adversarial.json).
- D. Regression cases -- every historical bug in tests/regression/ (+ registry tests/regression/REGRESSIONS.md, manifest datasets/regression.json).
- E. Full dataset -- 250 requests.csv rows through production pipeline + output validator + eval harness + regression/adversarial suites.

## Reporting (27.4)

scripts/eval_report.py --tag baseline|final writes baseline + final
(dataset, version, timestamp, test count, metrics, failures), failure
categories, honest improvement deltas (final minus baseline; regressions reported,
never hidden), and remaining failures with case/category/expected/actual/root
cause/severity/status.

## Ablation (Section 28)

scripts/run_ablation.py reproduces E0-E7 with comparison tables
(decision/plan accuracy, evidence, invalid outputs, tokens, cost, runtime) and
per-component KEEP/REMOVE/REVISE/OPTIONAL rulings. Rule: keep a component only
when its measurable value justifies its complexity.
