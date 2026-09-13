# Evaluation Strategy (LOCAL PROXY — NOT official HackerRank score)

## Structural

Valid rows (250+header), exact 8-col order, unique `request_id`s, input/output order match.

## Numerical

`0 <= safe <= requested`; `safe` accuracy vs `sample_requests` (MAE/within-x%);
`earliest` date accuracy (exact / ±days); plan arithmetic (partial sums to requested;
installments equal option totals).

## Decision

Status accuracy, method accuracy (esp. partial-5-conds, installment-exactness, wait-vs-later).

## Plan/safety

No invariant violations on re-simulation (balance floor, deadline); spending changes
flex-only/≤3/no-dup-mutation; FX/date determinism; double-run identical output.

## Evidence/explanation

Evidence IDs exist + belong to request/user; explanation facts ⊆ validated facts;
no invented numbers/dates; status↔method↔plan↔earliest consistency.

## Ablation (keep only measured wins)

| Ver | Adds | Decision | Plan | Invalid↓ | Evid | Tokens | Cost |
|---|---|---|---|---|---|---|---|
| E0 | structured deterministic | | | | | 0 | 0 |
| E1 | +messages | | | | | | |
| E2 | +images | | | | | | |
| E3 | +conflicts | | | | | | |
| E4 | +optimizer | | | | | | |
| E5 | +explanations | | | | | | |
| E6 | +validation | | | | | | |
| E7 | +token trim | | | | | | |

Results → `evaluation/reports/`. Token/cost of FINAL run → `evaluation/usage_report.md`.
