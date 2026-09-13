# Ablation Results E0-E7 (LOCAL MEASUREMENT -- OFFICIAL score UNKNOWN)

| Version | Decision Accuracy | Plan Accuracy | Evidence | Invalid Outputs | Tokens | Cost | Runtime |
| ------- | ----------------- | ------------- | -------- | --------------- | ------ | ---- | ------- |
| E0 | status 0.40 / method 0.40 | earliest-exact 0.36 | ev_err 11 | cons_err 0 | 0 | 0.00 | 2.07s |
| E1 | status 0.44 / method 0.48 | earliest-exact 0.36 | ev_err 11 | cons_err 0 | 0 | 0.00 | 2.11s |
| E2 | status 0.44 / method 0.48 | earliest-exact 0.36 | ev_err 0 | cons_err 0 | 0 | 0.00 | 2.03s |
| E3 | instrumented | instrumented | 132/250 w/ facts | 0 | 0 | 0.00 | -- |
| E4 | instrumented | instrumented | -- | 0 | 0 | 0.00 | -- |
| E5 | -- | -- | -- | 0 | 0 | 0.00 | -- |
| E6 | -- | -- | prod_err 0 | 0 | 0 | 0.00 | -- |
| E7 | -- | -- | -- | 0 | 0 | 0.00 | 2.03s |

*Sample accuracy vs sample_requests.csv (illustrative, NOT eval labels) -- calibration diagnostics only.

| Component | Benefit | Cost | New Failures | Decision |
| --------- | ------- | ---- | ------------ | -------- |
| E0 deterministic baseline | required core; 0 tokens, validator green | 0 tokens | 0 | KEEP |
| E1 +message interpretation | status +0.04 / method +0.08 vs E0; facts reach 132/250 | 0 tokens | 0 | KEEP |
| E2 +image linkage | evidence errors 11->0; blank!=0 | 0 tokens | 0 | KEEP |
| E3 +conflict handling | precedence unit-proven; 132/250 affected | 0 | 0 | KEEP |
| E4 +optimizer | tie-break deterministic; 6 multi-cand, diverged 0 | 0 | 0 | KEEP |
| E5 +grounded explanation | consistency 250/250 (rate 1.00) | 0 | 0 | KEEP |
| E6 +validation | production errors 0; all_controls_caught=True | 0 | 0 | KEEP |
| E7 +token accounting | 0 calls / 0 tokens at equal accuracy; runtime 2.03s | 0 | 0 | KEEP |

## Component instruments (production pipeline)

- E3 conflicts: 132/250 requests carry message facts (29 cancel/settle, 92 amend/delay). Rule: cancel/settle/amend > newer same-source > settled > safer; LLM never reorders
- E4 ranking: 6 multi-candidate requests; ranking changed winner on 0. Rule: deadline -> no-changes -> min total -> earlier start -> fewer payments -> lowest option id
- E5 explanations: 250/250 valid (rate 1.000). Rule: facts subset of validated Decision; no invented amounts/dates/evidence
- E6 validator: production errors 0; negative controls {'reordered_rows_caught': True, 'invented_enum_caught': True, 'out_of_bounds_safe_caught': True, 'bogus_plan_caught': True} (all caught=True). A validator catch is validator SUCCESS, not validator failure.
- E7 tokens: 0 calls, 0 tokens, 2.03s for 250 requests. image resolution only for blank amounts (16); message interpreter deterministic-only; LLM off by default

## Deltas

- E1-E0 status +0.04 method +0.08
- E2-E1 status +0.0 method +0.0 evidence_errors -11
- Sample rows are illustrative format examples, NOT eval labels; deltas are calibration diagnostics, not official gains.

## Keep/remove

- E0 deterministic baseline: **KEEP** -- required core; 0 tokens, validator green
- E1 message interpretation: **KEEP** -- sample status +0.04/method +0.08 vs E0; facts reach 132/250 requests; deterministic-only, 0 tokens
- E2 image linkage: **KEEP (as UNKNOWN-safe linkage)** -- evidence errors 11->0; blank!=0 enforced
- E3 conflict handling: **KEEP** -- precedence unit-proven; deterministic authority, LLM never reorders
- E4 optimizer: **KEEP** -- deterministic tie-break guarantee (unit-proven); 6 multi-candidate requests, diverged 0; near-zero cost so determinism justifies it
- E5 grounded explanation: **KEEP** -- consistency 250/250; fallback only, never recomputes finance
- E6 validation: **KEEP** -- production errors 0; all_controls_caught=True
- E7 token accounting: **KEEP** -- 0 calls / 0 tokens at equal accuracy; selective triggers keep runtime bounded

production_hash=620bff42124b0c3d (deterministic replay key)
