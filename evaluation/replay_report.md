# Replay Report — determinism (2026-09-13 ~17:30 IST)

## Runs

- Run 1: `python scripts/build_output.py --dataset dataset/official --out evaluation/local/replay_a.csv` → 250 rows, mix 33/182/29/6, SHA256 `d8386548517835c9542278d426dcd815edebf921b12292d5f1be87b480f8bca6`
- Run 2: same command → `evaluation/local/replay_b.csv` → identical mix, identical SHA256
- Reference: `output.csv` → identical SHA256 (`d838…ca6`), unchanged in git (no diff)

## Comparison

- Same request count: YES (250/250/250)
- Same order: YES (0 order mismatches vs `requests.csv`)
- Same deterministic financial state: YES (state.build pure; no LLM/clock/random imports — see `test_no_llm_or_clock_in_deterministic_core`)
- Same simulation: YES (forecast.simulate pure floor gate)
- Same candidate plans: YES (payment_plans.generate deterministic; optimizer 6-tuple rank_key)
- Same ranking: YES (reversed-input tie test green)
- Same output serialization: YES (byte-identical CSV incl. header)

## Manifest (stable hashes, no volatile timestamps in content)

- `output.csv`: `d8386548517835c9542278d426dcd815edebf921b12292d5f1be87b480f8bca6`
- `replay_a.csv`: same; `replay_b.csv`: same
- Intermediate artifacts (state/candidates/ranking) are compared via unit + chain tests (`test_chain_deterministic_double_run`, optimizer tie tests) rather than separate files — no intermediate dump exists by design (single canonical Decision → serializer).

## Differences

- None in deterministic sections. Volatile-only: `usage_report.md` wall-runtime field (2.4→2.9s) and `llm note` unchanged; wall-clock timestamps inside trace files are informational only (trace IDs are `sha256(run|request|index)` deterministic).
- Classification: NO unexpected nondeterminism. EXPECTED nondeterminism: none observed (model backend adds 0 facts in this config; metered vs E0 outputs identical).

## FINAL: PASS
