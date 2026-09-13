# Full-Dataset Verification — Sections 39–42 run (2026-09-13 ~17:30 IST)

## Official dataset

- dataset: `dataset/official`
- requests: 250 rows (`requests.csv` SHA256 `F94255BA…228225F78`)
- financial_events: `F6A7CCF2…5023BBD25F1F`
- financial_profiles: `B91B4CCB…F71550CF86500`
- request_payment_options: `AEDADF63…1BAAE01D8AC91F22`
- exchange_rates: `3DE3877E…A1580649B1BF3E3`
- messages: `FD9E3A1A…76FAABB8C427D107F4724EF52A3`
- images: `C5A3F168…CA90F7D2D34BAA1F9` (16 PNGs present)
- sample_requests: `1195BBE9…E6E59DAB75B9228C5DC`
- source mutation check: `git diff --stat -- dataset/official` → clean (no changes)

## Run

- command: `python scripts/build_output.py --dataset dataset/official --out output.csv`
- start/end: 2026-09-13 ~17:30 IST, wall ~2.8s (usage_report runtime field volatile: 2.4→2.9s across identical runs)
- processed: 250, succeeded: 250, failed: 0, retries: 0 (deterministic path), fallbacks: 0 decisions
- mix: affordable_now 33 / not_affordable 182 / affordable_with_plan 29 / affordable_later 6
- output: `output.csv` 250 rows + header, SHA256 `d8386548517835c9542278d426dcd815edebf921b12292d5f1be87b480f8bca6`
- input_rows 250 / output_rows 250 / missing 0 / extra 0 / duplicate 0 / order_mismatch 0 (measured, not inferred)

## Traces

- per-request traces: `evaluation/local/trace_request_26/28/30/33.json` + fallback trace (request→evidence→facts→state→forecast→candidates→rejected→selected→decision→output); no secrets

## Token usage (ESTIMATED, never provider-exact)

- provider: groq; models: qwen/qwen3.6-27b (66 calls) + groq/compound (11 calls)
- calls 77 / input 7864 / output 0 / total 7864 / avg 31.5 per request
- estimated total cost: UNKNOWN (no verified pricing); per-request: UNKNOWN
- source: `evaluation/usage_report.md` (metered run; E0 config stays 0/0/0.0000; decisions byte-identical either way)
- 0 facts added by model calls (no-backend records); safety unaffected

## Validators

- output validator: PASS (`scripts/validate_output.py --dataset dataset/official`)
- financial invariant: PASS (floor gate in `forecast.simulate`, boundary tests green)
- evidence validator: PASS (`validate_evidence` 0 errors; `eval_final` evidence_validity 0)
- regression: PASS (`pytest tests -q` 354 passed this turn)
- security scan: PASS (0 real hits; only `redact.py` regex self-match + test fixtures)

## Failures

- none. Failure classes tracked: INPUT/MODEL/TOOL/PARSING/VALIDATION/FINANCIAL/EVIDENCE/OUTPUT/ENVIRONMENT/UNKNOWN — 0 in all 12 eval failure categories.

## FINAL: PASS
