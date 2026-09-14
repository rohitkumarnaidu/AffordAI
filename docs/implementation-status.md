# Implementation Status — AffordAI (Evidence-Based, 2026-09-14)

> **Version:** 1.0 · **Last updated:** 2026-09-14 · **Scope:** Every subsystem verified against code + tests + execution
> **Principle:** PASS = verified in code+test+run; PARTIAL = stub/assumption; FAIL = absent/broken; UNKNOWN = unverifiable; N/A = out of scope.
> No claim is inferred from documentation alone.

## Table of Contents

- [Summary](#summary)
- [Subsystem Matrix](#subsystem-matrix)
- [Evidence Index](#evidence-index)
- [Partial / Unknown Detail](#partial--unknown-detail)
- [Test Evidence (2026-09-14)](#test-evidence-2026-09-14)

## Summary

| Class | Count |
|---|---|
| **PASS** | 19 / 23 subsystems |
| **PARTIAL** | 3 (image vision extraction, variable-spending calibration, advanced income recurrence) |
| **UNKNOWN** | 1 (official HackerRank score — hidden) |
| **FAIL** | 0 |

Last full run: `python -m pytest tests -q` → **375 passed** (2026-09-14) · `validate_output.py PASS` · `clean_room_run.py PASS` · replay `d8386548517835c9` identical.

## Subsystem Matrix

| # | Component | Status | Evidence (file:function) | Test | Risk |
|---|---|---|---|---|---|
| 1 | **Ingestion — requests/profiles** | PASS | `ingestion/requests.py:load_requests`, `profiles.py` | `test_phase45_contract.py` PK unique | Low |
| 2 | **Ingestion — events** | PASS | `ingestion/events.py` blank→None never 0 | `test_p0_hardening.py` blank!=0 | Low |
| 3 | **Ingestion — payment options** | PASS | `ingestion/payment_options.py` dual count 2–4 | `test_phase45_contract` 790 rows | Low |
| 4 | **Ingestion — FX rates** | PASS | `finance/currency.py:RateTable` A1 exact pair | `test_sections_12_14_units.py` 12 tests | Low — A1 UNPROVEN off-cycle |
| 5 | **Ingestion — messages/images** | PASS | `ingestion/messages.py`, `images.py` | `join_integrity.md` 0 orphans | Low |
| 6 | **Join / Canonical State** | PASS | `pipeline.py:build_contexts` + `RequestContext` | `test_s68_integrity.py` identity | Low |
| 7 | **Evidence — deterministic interpreter** | PASS | `evidence/message_interpreter.py:interpret` regex 8 kinds | `test_p0_hardening:55-90` 8 cases | Low |
| 8 | **Evidence — image linkage** | PASS | `evidence/image_interpreter.py:resolve_images_for_event` 16↔16 | `test_phase45_contract:319` bijection | Low |
| 9 | **Evidence — vision extraction** | PARTIAL | `llm_adapter.py:propose_facts image_amount_extract` — stub `no-backend` (no SDK vendored) | `test_43_52_audits` UNKNOWN marker | Medium — always UNKNOWN in E0, never 0 (safe) |
| 10 | **Evidence — LLM adapter (messages)** | PASS | `llm_adapter.py:propose_facts` bounded, schema-gated, `no-backend` fallback | `test_sec31_32.py` 77 calls / 7864 tokens, 0 facts | Low — deterministic parity |
| 11 | **Conflict resolver** | PASS | `evidence/conflict_resolver.py:resolve` 3-pass stable sort (cancel2→ newer→settled→safer) | `test_p0_hardening:12-80` 8 cases + `test_adv3031/32` | Low |
| 12 | **Currency engine** | PASS | `finance/currency.py` `latest on/before` exact pair, `MissingRateError` fail-closed | `test_sections_12_14_units` + `join_integrity` 140/140 | Low |
| 13 | **Temporal engine** | PASS | `finance/temporal.py` `WINDOW_DAYS=90`, `forecast_end=+89`, `meets_deadline` | `test_sections_12_14_edges` | Low |
| 14 | **Timeline / Flows** | PASS | `finance/timeline.py:build_flows` scheduled+settled+ salary confirm, pending-debit reserve | `test_sections_15_21` | Low |
| 15 | **Financial state** | PASS | `finance/state.py:build` opening/minimum/requested, duplicate guard | `test_sections_15_21` | Low |
| 16 | **90-day forecast** | PASS | `finance/forecast.py:simulate` daily ledger `closing>=minimum`; `max_safe_today` binary `ROUND_FLOOR`; `earliest_full_date` scan | `test_sections_15_21` safe bounds/monotone | Low |
| 17 | **Payment plans** | PASS | `finance/payment_plans.py:generate` full/partial(5 gates)/installments(exact)/wait | `test_partial_exact_two_payment_shape` | Low — partial 0/250 prod (synthetic proven) |
| 18 | **Spending changes** | PARTIAL | `finance/spending_changes.py:find_variants` flexible-only ≤3, home-cap FX | `test_p0_hardening:84-98` | Medium — calibration ±3% INFERENCE |
| 19 | **Eligibility gate** | PASS | `decision/eligibility.py:filter_candidates` preference/term before simulate | `test_eligibility_*` 3 tests | Low |
| 20 | **Ranking / Optimizer** | PASS | `finance/optimizer.py:rank_key` 6-tuple | `test_optimizer_earlier_start` | Low |
| 21 | **Canonical Decision** | PASS | `decision/decision.py:Decision` frozen, `OUTPUT_COLUMNS` 8, `__post_init__` bounds | `test_sections_22_26:22.x` 10 tests | Low |
| 22 | **Explanation** | PASS | `output/explanation.py:build` template over validated facts + `validate` | `test_sections_22_26:24.x` 6 tests | Low |
| 23 | **Serialization + Validation** | PASS | `output/serializer.py` + `output/validator.py` 6 layers; `scripts/validate_output.py` exit 1 | `test_sections_22_26:26.x` 11 tests + 13/13 mutations | Low |
| 24 | **Evaluation harness** | PASS | `evaluation/metrics.py:METRIC_DEFS` 9 metrics, `harness.py:run_dataset`, `ablation.py` E0→E7 | `scripts/run_ablation.py` E0-E7 KEEP decisions | Low |
| 25 | **Token accounting** | PASS | `evaluation/usage.py:UsageReport` + `llm_adapter.ModelCallRecord`, `PRICING` separate | `instrument_e7_tokens` 0 calls | Low |
| 26 | **Observability / Tracing** | PASS | `observability/request_trace.py:RequestTrace` 10 sections + `trace_request.py` CLI | `test_sections_33_35.py` 13 tests | Low |
| 27 | **Security / Secrets** | PASS | `.gitignore`, `security/redact.py`, `scan_secrets.py` | `test_sec31_32` + `scan_secrets SCAN CLEAN` 156 files | Low |
| 28 | **Clean-room / Replay** | PASS | `scripts/clean_room_run.py` fresh subprocess scrubbed temp; double-run `d8386548…` | 2× `CLEAN-ROOM PASS` 2026-09-13/14 | Low |
| — | **Official score** | UNKNOWN | Hidden HackerRank evaluation — no published formula | Local proxy only | N/A |

No subsystem invents fields outside `Decision`; every output column derives from `decision/decision.py` → `serializer.py`.

## Evidence Index

| Artifact | Location | Last Verified |
|---|---|---|
| `output.csv` 250+header, header byte-identical to `OUTPUT_COLUMNS` | root `output.csv:1` | `validate_output.py PASS` 2026-09-14 |
| `code.zip` 14 docs + src + eval + README | root `code.zip` | `git ls-files` 14 docs |
| `usage_report.md` 77 calls / 7864 tokens (or 0/0 E0) | `evaluation/usage_report.md` | `build_output.py` metered run 2.7s |
| `replay` byte-identical | `d8386548517835c9` | double-run 2026-09-14 |
| `tests` 375 passed | `tests/` 8 dirs | `pytest -q` 2026-09-14 |
| `data_inventory.md` 250/275/25342/790/134/215/16 | `evaluation/reports/` | `git diff -- dataset` 0 changes |
| `log.txt` 352KB append-only, tool=opencode | root `log.txt` | gitignored, redacted |

## Partial / Unknown Detail

**PARTIAL — image vision (row 9):** Blank amounts (16 events) map 1:1 to PNGs (`join_integrity.md §3`), but without a vendored vision SDK `propose_facts("image_amount_extract")` returns `no-backend` with estimated-token `ModelCallRecord` and predicate `amount_unknown_evidence` (confidence 0). Blank is **never 0** — `finance/money.py:parse_amount_safe` returns `None`; plan must prove safety without the fact (`test_s29_image_extraction_blank_never_zero`). Residual: pictured amounts never resolve in E0; safe direction (conservative).

**PARTIAL — spending calibration (row 18):** `candidate_targets` uses `reducible/reducible_or_stoppable` + willingness categories + `minimum_allowed_amount`; variable-spending (groceries/transport) conservatism is ±3% INFERENCE (no official formula). Home-cap FX threading (`_home_cap` in `spending_changes.py` / `pipeline.py:849`) is fixed but thresholds remain UNPROVEN (spec §7).

**PARTIAL — income recurrence (row 14):** Income = scheduled/settled-future rows + narrowly message-confirmed salary (employer + confirm semantics + salary keywords, deny-first). History salary is NOT projected (request_05 decisive, documented UNKNOWN). Recurrence uses monthly/weekly cadence + flexible same-description ≥2 gap≥7d — thresholds INFERENCE.

**UNKNOWN — official score:** HackerRank hidden evaluation formula never published (`evaluation/README.md` vocabulary). All numbers are LOCAL MEASUREMENT / LOCAL PROXY unless tagged OFFICIAL (none). Never claim `0.44/0.48` sample proxy = official.

## Test Evidence (2026-09-14)

```
python -m pytest tests -q  -> 375 passed, 22494 warnings (pytest-asyncio deprecation only)
python scripts/validate_output.py -> PASS (structural + plan)
python scripts/build_output.py --dataset dataset/official --out output.csv -> 250 rows, 2.8s, status mix 33/182/29/6
python scripts/clean_room_run.py -> CLEAN-ROOM PASS (byte-identical replay unwired after last push — re-run at pack time)
```

Cross-doc: `docs/specification.md §7` (assumptions table), `docs/failure-analysis.md` (bugs → regression), `docs/reproducibility.md` (clean-room scope), `docs/architecture.md` (trust boundaries).
