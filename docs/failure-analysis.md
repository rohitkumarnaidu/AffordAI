# Failure Analysis — AffordAI

> **Version:** 1.0 · **Last updated:** 2026-09-14 · **Scope:** Every critical failure class discovered — symptom → root → impact → fix → regression → prevention
> **Philosophy:** `BUG → ROOT CAUSE → FIX → REGRESSION TEST` — fix the rule, not one example.

## Table of Contents

- [Critical Classes (8, from Prior Orchestrate)](#critical-classes-8-from-prior-orchestrate)
- [Pipeline Failures (5 Real Fixes)](#pipeline-failures-5-real-fixes-on-this-repo)
- [Latent Bugs Found & Fixed Zero-Impact](#latent-bugs-found--fixed-zero-impact-on-official-data)
- [Residual Risks](#residual-risks)
- [Prevention System](#prevention-system)
- [Regression Registry](#regression-registry)

## Critical Classes (8 from Prior Orchestrate)

| # | Symptom | Root Cause | Impact | Fix | Regression Test | Prevention |
|---|---|---|---|---|---|---|
| **F1** | Row-order corruption — output row 7 maps to request 19 | No `original_index` preservation; `groupby`/`async` reorders | Wrong user gets decision | `RequestContext(original_index, request_id, user_id)` + `serializer.decisions_to_rows` sorted by `original_index` | `test_s68_integrity.py:row_order`, `test_m1_row_order_invariance` | Validator checks `req_ids == out_ids` ordered; reverse fails |
| **F2** | Weak evidence grounding — non-existent evidence IDs in explanations | No `EvidenceRegistry` ownership check | Fabricated provenance | `EvidenceRegistry(valid_event_ids, valid_message_ids, valid_image_ids).add` allowlist + `check_batch_safe` | `test_s29_evidence_mismatch_rejected`, `test_untrusted cross-request` | `validator.validate_evidence` 0 invented |
| **F3** | Incorrect earliest rule — `earliest` treated as preference-filtered date | `earliest` computed after eligibility filter | Tier-1 violation: capacity independent of preferences | `forecast.earliest_full_date(state)` single-state sig, before `filter_candidates` | `test_earliest_independent_of_preferences` | `invariants.check_earliest_consistency` |
| **F4** | Generic explanations — "Unable to determine" filler | No `explanation.validate` | Judge penalty | `explanation.build` WHY+CONSTRAINT+PLAN+TIMING+EVIDENCE + `validate` filler reject | `test_sections_22_26:24.x` no-generic | E5 instrument 250/250 consistent |
| **F5** | Missing evidence → treated as no-op | Blank amount → silent None without UNKNOWN marker | Unsafe “free expense” if zero-assumed | `money.parse_amount_safe` blank→None + `amount_unknown_evidence` confidence 0 | `test_s29_image_extraction_blank_never_zero`, 16↔16 bijections | Validator + spec §6 blank≠0 |
| **F6** | Fragile modality — every image blindly sent to vision | No `needs_llm_for_image` linkage | Cost ×16, hallucination | `pipeline:_collect_evidence` selective: only blank + file_exists | `ablation E2 ev 11→0` | Linkage log `resolve_images_for_event` |
| **F7** | Open-ended AI instructions | No schema allowlist, confidence gate | Injection overrides floor | `llm_adapter._validate_proposal` strict gate + `min_confidence` + `kind==amount` filter + `parse_amount>0` | `test_untrusted` 4 injection variants inert | `threat-model.md` 30.4 prompt-injection non-positive/unlinked |
| **F8** | Interface drift — `OUTPUT_COLUMNS` forked between modules | Columns defined in two places | Header mismatch | Single source `decision/decision.py:OUTPUT_COLUMNS` + `serializer.EXACT_COLUMNS==OUTPUT_COLUMNS` | `test_sections_22_26:25.x` header byte-match | Build-checklist module 22 |

All 8 covered by `test_sections_27_30_regression.py` (15 groups) + `tests/regression/REGRESSIONS.md` (R01–R05).

## Pipeline Failures (5 Real Fixes on This Repo)

| # | Symptom | Root → Fix | Test |
|---|---|---|---|
| **P1** | Tier-1 earliest blank for `affordable_with_plan` flagged as error | `validator.validate_consistency` required `earliest` non-empty for `with_plan` — wrong (installments without single-payment capacity is valid, 4 rows) → `invariants.py:13-32` strict map: `with_plan` allows empty `earliest` when no single-payment capacity but installments safe | `test_earliest_strict` + `output.csv` 250 PASS |
| **P2** | Validator rejected `affordable_later` with `wait` that was actually valid | `affordable_later` mapped only to `wait` but validator permissively allowed `full`/`installments` — fixed to strict `later→wait` + `earliest>request_date` | `test_status_method_strict` |
| **P3** | `dataset/` vs `dataset/official/` path hardcode — evaluator uses `dataset/` | `pipeline._resolve_dataset_path` tried only `dataset_dir/filename` → added fallback `dataset_dir/official/filename` | `test_ingress_reorder_stable` dual-layout both PASS |
| **P4** | Mixed `date`/`datetime` sort crash on `sent_at` with `T09:30:00Z` | `conflict_resolver` sorted `sent_at` str vs datetime — `str()` hardening | `test_m3_balance_monotonicity` + `test_r6_fallback_never_crashes` |
| **P5** | Dead imports masked missing wiring (`forecast_mod`, `RateTable`, `Evidence`) | Lint: unused imports in `pipeline.py`, `forecast.py` → removed, wired `regression.snapshot/drift` into `evaluate.py` | `test_43_52_audits` |

Sample forensics drove 5 fixes: pipe-split `|` preference parse, payroll-ref `EMP-0001` poisoning guard, salary linkage employer+confirm, debt/income recurrence bounds, sent_at vs event_date precedence — all in `test_p0_hardening.py:12-230`.

## Latent Bugs Found & Fixed Zero-Impact (Proven)

Conditions measured on official 250/25342/215 before fixing — post-fix replay byte-identical (`d8386548517835c9`):

| Bug | Condition on Official Data | Fix | Proved Zero-Impact |
|---|---|---|---|
| **L1 reduce-FX unit mix** | 0 cross-currency reducible-with-floor events | `_home_cap` home-currency caps + rate threading (`spending_changes.py`, `pipeline.py:849`, `ablation.py:280`) | `ablation` flow diff 0 |
| **L2 salary-link any-source** | 0 `_link_salary_fact` firings (all salary confirms already gated) | `pipeline.py:_link_salary_fact` employer/bank + confirm + deny-veto gates | `message_income` flow diff 0 |
| **L3 receipt `1110` vs 393.22 INR** | `message_86` unlinked + settled-past + no recurrence + single-request user | Year-guard `_first_valid_amount` + `_is_negated` cancel/delay guard | `build_flows` 0 flow diff |
| **L4 year fragments** | 6 msgs with `20xx` fragments, all unlinked-inert | `_first_valid_amount` year guard (`message_interpreter.py`) | No amount fact emitted |
| **L5 negated cancel** | 0 linked cancels | `_is_negated` guard | No cancelled_set diff |
| **L6 weak boundary test** | — | Hardened `test_no_llm_or_clock_in_deterministic_core` glob all core modules | `pytest 375 PASS` |

## Residual Risks

| Risk | Why Unresolved | Mitigation |
|---|---|---|
| Income = scheduled/settled-future + narrowly confirmed salary only; history salary not projected | `request_05` decisive vs sample — no Tier-1 recurrence formula published | Narrow confirm + `spec §7` UNKNOWN, per-request fallback `not_affordable` is safe | 
| FX A1 `latest on/before` exact directed pair off-cycle | 140/140 holds, but pre-`2023-10-15` minus 702 events would need fallback | Fail-closed (`MissingRateError` excludes foreign credit) — safe |
| Variable-spending calibration ±3% | No official conservative formula | Home-cap + ≤3 changes + `simulate` floor — err conservative |
| Partial 0/250 production | 0 rows meet all 5 gates | Synthetic regression covers all gates (`test_partial_exact_two_payment_shape`) |
| `code.zip` lags gate scripts | Zip predates `final_red_flag_gate.py` + `final_green_light_gate.py` added after last rebuild | Rebuild at pack time + `clean_room_run.py` |
| Vision never resolves in E0 | No vendored SDK | UNKNOWN marker, plan safe without it — correct per spec |

All risks documented in `docs/specification.md §7` tagged `[UNPROVEN]` / `PARTIAL`.

## Prevention System

| Mechanism | How | Evidence |
|---|---|---|
| **Validator gate** | `scripts/validate_output.py` exit 1 on any `ValidationError` — blocks submission | `validate_all` 6 layers, 13/13 mutations REJECTED |
| **Red-flag + green-light gates** | `scripts/final_red_flag_gate.py` 12 checks (re-derive safe+earliest, re-simulate), `final_green_light_gate.py` checklist | `MODULE 39` CONDITIONAL GREEN |
| **Regression registry** | `BUG → ROOT CAUSE → FIX → REGRESSION TEST`; `tests/regression/REGRESSIONS.md` R01–R05 + 15 groups | `tests/regression/test_sections_27_30_regression.py` 15/15 |
| **Adversarial suite** | 29 threats 5 cats + 4 legacy injection tests | `tests/adversarial/test_sections_27_30_threats.py` 29 PASS |
| **Clean-room + replay** | Fresh subprocess scrubbed temp; double-run sha256 identical | `d8386548517835c9` + `clean_room_run.py PASS` |
| **Secret scan** | `scripts/scan_secrets.py` 156 files, header-only fixtures whitelisted | `SCAN CLEAN` |
| **AI-boundary proof** | `test_no_llm_or_clock_in_deterministic_core` grep core modules | `finance/*`, `decision/*`, `output/validator` LLM-free |
| **Deterministic core** | Binary `max_safe` `ROUND_FLOOR`, 6-tuple `rank_key`, `original_index` sort | `test_chain_deterministic_double_run` |

## Regression Registry

| ID | Class | Test | Lesson |
|---|---|---|---|
| R01 | Row-order | `test_s68_integrity` | Original_index preservation |
| R02 | Evidence mismatch | `test_s29_evidence_mismatch_rejected` | Provenance + ownership |
| R03 | Cancellation | `test_s29_cancellation` | cancel>amend |
| R04 | Amendment | `test_s29_amendment` | amended_amounts re-maps flows |
| R05 | Image blank!=0 | `test_s29_image_extraction_blank_never_zero` | UNKNOWN marker |
| R1 | Tier-1 earliest | `test_r*_tier1_earliest` | Independence from preferences |
| R2 | Pipe-split | `test_p0_hardening pipe` | `\|`-split not comma |
| R3 | Payroll-ref poisoning | `test_p0_hardening payroll` | `EMP-xxx` not an amount |
| R4 | Salary linkage | `test_p0_hardening salary` | Employer+confirm+salary keywords |
| R5 | sent_at precedence | `test_p0_hardening sent_at` | ISO vs event_date |
| R6 | Per-request fallback | `test_r6_per_request_fallback_never_crashes_batch` | `_decide_safe` |
| S29-* | 15 required groups | `test_sections_27_30_regression` | Each one production-path |
| S44  | Red-flag re-derivation | `scripts/final_red_flag_gate` | Safe+earliest re-proved |
| F1-F2 | Home-cap FX + salary gate etc. | `test_sections_43_52_audits` 14 tests | Proved 0-impact |

Full catalog: `tests/regression/REGRESSIONS.md`.

Cross-doc: `docs/implementation-status.md` (status per component), `docs/threat-model.md` (adversarial 29), `docs/reproducibility.md` (clean-room scope), `evaluation/reports/` (ablation + eval).
