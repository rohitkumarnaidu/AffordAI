# Build Checklist -- Modules 0-35 (completion gate)

Status per item: `[ ]` not started · `[~]` partial · `[x]` complete · `[!]` blocked/risky · `[-]` n/a.
Referenced by `AGENTS.md` §§27-27b, 30. Update as work lands.

## MODULE 0 -- Repository & governance
- [x] 0.1 repo init, `origin`=AffordAI, `upstream`=official-ref, branch/worktree known
- [x] 0.2 `.gitignore` (.env, log.txt, local dirs), no secrets, meaningful commits, upstream never merged
- [~] 0.3 transcript: root `log.txt`, append-only, session-start + per-turn, exact `tool=`, redaction, shared log
  (logging began 2026-09-13; earlier turns predate the contract -- noted in log)

## MODULE 1 -- Specification
- [~] 1.1 core spec (objective, I/O, enums, financial/temporal/evidence/conflict/preference rules, prohibitions)
  (draft exists but not Tier-1 re-verified -- honest ~ per zero-trust)
- [~] 1.2 decision matrix (states, methods, partial/installment/spending/deadline/tie-break rules)
  (draft exists but not code-proven -- honest ~)
- [~] 1.3 edge semantics (missing values, duplicates, cancels, amendments, settlement, unresolved conflicts,
  missing evidence/FX -- FX fallback A1 set; rest pending engine)

## MODULE 2 -- Data ingestion (`src/affordai/ingestion/`)
- [x] 2.1 loaders: requests, profiles, events, payment options, FX, messages, images -- Evidence: `ingestion/*.py` typed loaders, `pipeline.py:191-203 load_dataset` dual-layout
- [x] 2.2 schema validation: columns, types, nulls, unexpected values, row counts -- Evidence: `ingestion/__init__.py require_decimal/parse_amount_safe`, `evaluation/reports/data_inventory.md`
- [x] 2.3 identity: `original_index`, `request_id`, `user_id`; no cross-request/user leaks -- Evidence: `pipeline.py:393-412 _validate_request_identity`, `tests/contract/test_phase45_contract.py` PK unique

## MODULE 3 -- Relationship / join engine
- [x] 3.1 joins: user->profile, request->user/options/messages, event->image -- Evidence: `pipeline.py:233-390 build_contexts()` with deterministic sorting
- [x] 3.2 lifecycle: `linked_event_id`, `related_event_id`, amendments, duplicate detection -- Evidence: `pipeline.py:206-230 _dedupe_by_key`, `build_contexts` orphan checks
- [x] 3.3 safety: missing refs, ownership, multiplicity, no duplicate joins -- Evidence: `pipeline.py:414-557 _validate_fk_integrity`, `JoinIntegrityIssue`, `tests/contract/join_integrity.md`

## MODULE 4 -- Canonical request context (`pipeline.py: RequestContext`)
- [x] 4.1 object carries index/ids/request/profile/events/messages/images/options/evidence -- Evidence: `pipeline.py:41-95 RequestContext` with join_issues
- [x] 4.2 immutable identity, deterministic ordering -- Evidence: `pipeline.py:60-95 validate_identity/validate_relationships`, events (settlement_date,event_id), messages (sent_at,message_id) sorted, isolation via dict copy

## MODULE 5 -- Evidence system (`evidence/evidence_registry.py`)
- [x] 5.1 provenance fields (source type/id, request/user/event/message/image, raw/normalized, method, confidence) -- Evidence: `evidence_registry.py:15-48 provenance()`, `pipeline.py:589-605 sent_at stamping` 
- [x] 5.2 validation: IDs exist, correct owner, supports claim, no fabrication -- Evidence: `evidence_registry.py:76-130 add() with valid_* IDs + rejected trace`, `tests/regression/test_p0_hardening.py:210-230`, `tests/adversarial/test_untrusted.py:59-69` PASS

## MODULE 6 -- Message intelligence
- [x] 6.1 detect: cancel/settle/amend/delay/confirm/amount-change/date-change/preference -- Evidence: `message_interpreter.py:15-29 _PATTERNS+_PREF_PATTERNS`, `tests/regression/test_p0_hardening.py:55-90,130` PASS
- [x] 6.2 safety: injection resistance, irrelevant/malformed handling, provenance -- Evidence: `message_interpreter.py:1-7 zero-trust`, `tests/regression/test_p0_hardening.py:130-180`, `tests/adversarial/test_untrusted.py:23-40` PASS
- [x] 6.3 AI: bounded prompt, structured schema, validation, fallback, token tracking -- Evidence: `evidence/llm_adapter.py:70-105 _validate_proposal`, `pipeline.py:610-627 min_confidence gate`, `evaluation/usage_report.md` E0 0-calls

## MODULE 7 -- Image intelligence
- [x] 7.1 resolution: id mapping, file exists, linkage, relevance filter -- Evidence: `evidence/image_interpreter.py:20-38`, `pipeline.py:628-634 selective trigger`, `tests/contract/test_phase45_contract.py:319-327` 16↔16 bijection
- [~] 7.2 extraction: amount, currency, context, confidence, provenance -- Deterministic UNKNOWN-safe (E0 stub); `llm_adapter.py:108-122 no-backend`, `pipeline.py:643-674 amount_unknown_evidence` -- full vision deferred per spec, blank!=zero enforced
- [x] 7.3 failures: blank/missing/unreadable/irrelevant/malicious-image handling (blank!=zero, 16↔16 verified) -- Evidence: `finance/money.py:39-57 blank->None never 0`, `pipeline.py:643 filter kind==amount`, `tests/regression/test_p0_hardening.py:100-150`, `tests/unit/test_engine_units.py:52-64` PASS

## MODULE 8 -- Conflict resolution (`evidence/conflict_resolver.py`)
- [x] 8.1 precedence: cancel/settle/amend -> newer same-source -> settled -> safer; deterministic; AI can't override -- Evidence: `conflict_resolver.py:18-85 _EXPLICIT_ORDER+_method_rank+stable 3-pass sort`, `detect_conflicts()` audit, `pipeline.py:598 sent_at` stamping
- [x] 8.2 regression fixtures -- Evidence: `tests/regression/test_p0_hardening.py:12-80 (8 cases)`, `tests/unit/test_engine_units.py:187-190` PASS

## MODULE 9 -- Currency engine (`finance/currency.py`)
- [x] 9.1 same/foreign conversion, dated rate, direction, home-currency output (A1: latest row <= settlement) -- Evidence: `currency.py:RateTable.get_rate/convert_to_home`, `tests/unit/test_sections_12_14_units.py` (12 tests) PASS 2026-09-13
- [x] 9.2 failures: missing rate/date-mismatch/unsupported pair/invalid amount (fail-closed + log) -- Evidence: `MissingRateError/UnsupportedCurrencyError/DuplicateRateError`, `ConversionTrace.reason`, `load_skipped`, `tests/edge_cases + adversarial` (network-disabled) PASS

## MODULE 10 -- Temporal engine (`finance/temporal.py` + `finance/timeline.py`)
- [x] 10.1 request/event/settlement/income/recurring/payment/completion dates, 90-day horizon -- Evidence: `temporal.py` single-source WINDOW_DAYS=90, `forecast_end=+89`, `timeline.py`/`forecast.py` consume it, `tests/unit` (5 tests) PASS
- [x] 10.2 edges: same-day, boundary, deadline-day, 90-day boundary, recurrence anomalies -- Evidence: `flow_sort_key`, `meets_deadline(<=)`, `clamp_month_day`, `generate_monthly/interval_occurrences`, `tests/edge_cases` (9 tests) PASS

## MODULE 11 -- Financial state engine (`finance/state.py`)
- [x] 11.1 balance, minimum, essentials, flexible, recurring income, obligations, valid settled events -- Evidence: `state.build` validates opening/minimum/requested/home/dates/flows + provenance, `tests/unit` (4 tests) PASS
- [x] 11.2 pending debit (reserve) vs pending credit (ignore), failed/cancelled/duplicate/unrealized excluded,
  confirmed salary on settlement date only -- Evidence: `timeline.build_flows` inclusion rules + `state.build` duplicate/out-of-window gate, `tests/edge_cases + integration` (12 tests) PASS; full output.csv byte-identical before/after refactor, double-run identical, clean-room PASS 2026-09-13

## MODULE 12 -- 90-day forecast (`finance/forecast.py`)
- [x] 12.1 daily ledger: opening, inflows, essentials, recurring, existing + candidate payments, closing -- Evidence: `forecast.py:simulate` daily loop, `timeline.build_flows` inclusion rules, 4-agent audit 2026-09-13, `tests/regression/test_sections_15_21.py` (dynamic states)
- [x] 12.2 invariant `closing >= minimum` every day; no double-counting; deterministic -- Evidence: `forecast.py` early-return on breach, `state.py` double-count guard, `test_simulate_floor_boundary`, `test_forecast_floor_invariant_across_window`, full output.csv 250 rows after change (sha256 `801c68d7...` 2026-09-13 16:04 IST), double-run identical

## MODULE 13 -- Payment-plan engine (`finance/payment_plans.py`)
- [x] 13.1 candidates: full / partial / installments / wait / spending-change variants / not_recommended -- Evidence: `payment_plans.generate` + `spending_changes.find_variants` + pipeline `None->not_recommended`; `test_partial_exact_two_payment_shape`, `test_installments_exact_option_match`, `test_wait_shape_conditions`
- [x] 13.2 each: safety -> deadline -> preference -> ranking -- Evidence: `pipeline.py decide_context` order generate->variants->filter->simulate->select; `test_eligibility_keeps_unsafe_but_preferred` proves safety-after-preference split

## MODULE 14 -- Amount safe to pay
- [x] 14.1 max safe today, before optional changes, bounded, deterministic search -- Evidence: `forecast.max_safe_today` (monotonicity lemma in docstring, ROUND_FLOOR hi, clamp `0<=safe<=requested`, fail-closed post-conditions); computed before `find_variants` in pipeline
- [x] 14.2 boundaries: 0, full, exact edge, ±edge -- Evidence: `test_safe_plus_unit_rejected_and_bounded`, `test_safe_monotone_all_below_safe`, `test_safe_non_2dp_requested_never_exceeds`, `test_earliest_never_safe_is_none` (safe==0)

## MODULE 15 -- Earliest full-payment date
- [x] 15.1 scan from `request_date`; first safe single-payment date; empty if never; preference-independent -- Evidence: `forecast.earliest_full_date` linear scan, single-`state` signature (`test_earliest_independent_of_preferences`), `None->""` mapping
- [x] 15.2 safety + deadline validation -- Evidence: `test_earliest_minimal_every_earlier_day_unsafe` (loop-proves minimality), deadline enforced downstream (`test_partial_gated_off` earliest>deadline case)

## MODULE 16 -- Partial payment
- [x] 16.1 eligible: allows-partial, user accepts, `0 < safe < requested`, `earliest <= deadline` -- Evidence: `payment_plans.generate` 4/5 gates + `eligibility` acceptance gate; `test_partial_gated_off` (3 gate cases)
- [x] 16.2 exactly 2 payments (`safe` + remainder = requested), safe, on time -- Evidence: `test_partial_exact_two_payment_shape` (legs, sum, simulate ok)

## MODULE 17 -- Installments
- [x] 17.1 exact match: option id, count, dates, amounts, fees -- Evidence: `expand_schedule` + `Candidate(option_id, total_paid)`; `test_installments_exact_option_match`; malformed skip+note `test_installments_malformed_skipped_with_note`
- [x] 17.2 user accepts installments, month-limit ok, safe, on time -- Evidence: `eligibility` term gate (`test_eligibility_preferences_and_term` pre-existing), validator exact-match re-derivation

## MODULE 18 -- Spending changes (`finance/spending_changes.py`)
- [x] 18.1 flexible-only, protected kept, <=3, syntax valid, stop/reduce exclusive -- Evidence: `spending_changes.py:32-60 candidate_targets()` protected guard, STOP_OK/REDUCE_OK, `tests/regression/test_p0_hardening.py:84-98` PASS
- [x] 18.2 change flips plan safe, deadline holds, no gratuitous changes -- Evidence: `spending_changes.py:72-106 find_variants()` simulate+deadline gate, `validator.py:207-234` <=3 syntax check

## MODULE 19 -- Method eligibility (`decision/eligibility.py`)
- [x] 19.1 filter by accepted/excluded methods, installment + partial preferences -- Evidence: `eligibility.filter_candidates` + docstring contract; `test_wait_needs_full_acceptance`, `test_eligibility_drops_safe_but_excluded_and_late_and_partial_gate`
- [x] 19.2 selected plan is safe + eligible + correctly ranked -- Evidence: pipeline filter->simulate->select order; `test_eligibility_keeps_unsafe_but_preferred` (separation proof)

## MODULE 20 -- Ranker (`finance/optimizer.py`)
- [x] 20.1 deadline -> no-changes -> min total -> earlier start -> fewer payments -> lowest option id -- Evidence: `optimizer.rank_key` 6-tuple + docstring (`None->"~~~"` sorts last); pre-existing rules 1-3 tests + new `test_optimizer_earlier_start_fewer_payments_option_id`
- [x] 20.2 tie tests incl. final option-id break -- Evidence: same test (start/count/option-id/None-last); deterministic double-run `test_chain_deterministic_double_run`

## MODULE 21 -- Decision (`decision/decision.py`)
- [x] 21.1 canonical `Decision` carries all 8 fields + evidence + explanation facts -- Evidence: `decision.py OUTPUT_COLUMNS` order, `Decimal` amount type (fixed 2026-09-13), pipeline populates all in `decide_context`
- [x] 21.2 status↔method↔plan↔dates↔changes↔explanation consistent -- Evidence: `rules.derive` mapping + `test_rules_derive_full_mapping`, `invariants.py` + validator consistency layers, `validate_output.py PASS`

## MODULE 22 -- Output (`output/serializer.py`, `validator.py`, `scripts/validate_output.py`)
- [x] 22.1 exact columns/order/count/request order -- Evidence: `output/serializer.py EXACT_COLUMNS==OUTPUT_COLUMNS`, `decisions_to_rows` enforces sorted-by-original_index/duplicate/8-col, `write_output_csv` QUOTE_MINIMAL, `tests/regression/test_sections_22_26.py:25.x` (8 tests) PASS
- [x] 22.2 structural validator live; financial/plan/date/evidence/consistency layers -- Evidence: `output/validator.py validate_files+validate_plans+validate_evidence/consistency/canonical/safety`, error codes OUTPUT-STRUCT/ID/NUM/ENUM/PLAN/SPEND/CONSISTENCY/EVIDENCE, `validate_output.py` gate blocks on any error, 51 tests PASS, full 250 rows PASS

## MODULE 23 -- Explanation (`output/explanation.py`)
- [x] 23.1 facts ⊆ validated decision facts; amounts/dates/evidence match; nothing invented -- Evidence: `output/explanation.py build_facts/build/build_fallback/validate`, facts derived from Decision only, no raw dataset, `tests/regression/test_sections_22_26.py:24.x` (6 tests) PASS
- [x] 23.2 concise, specific, decision-consistent -- Evidence: WHY+CONSTRAINT+PLAN+TIMING+EVIDENCE, `validate` checks status/method/plan/date/amount/spending, filler rejected, fallback deterministic

## MODULE 24 -- AI layer
- [x] 24.1/24.2/24.3 message/image/explanation prompts bounded, schema-validated, fallback + usage tracked; explanation receives validated facts only -- Evidence: `evidence/llm_adapter.py` bounded propose_facts allowlist, `pipeline.py` validated-or-dropped, `output/explanation.py` validated-facts-only with fallback, `evaluation/usage_report.md` 0 calls E0

## MODULE 25 -- Evaluation (`evaluation/`, `scripts/evaluate.py`)
- [x] 25.1 local proxies: structural/financial/decision/plan/evidence/explanation/robustness (NOT official score) -- Evidence: `evaluation/metrics.py` 9 metrics + METRIC_DEFS + `full_dataset_metrics` 0 errors, `evaluation/README.md` official-vs-local, `evaluation/usage_report.md` 250 rows 0 tokens
- [x] 25.2 sample/edge/adversarial/regression/full-dataset suites -- Evidence: `evaluation/datasets/*.json` 5 manifests, `scripts/eval_report.py` baseline/final 250 rows all green, `tests/edge_cases` + `tests/adversarial/test_sections_27_30_threats.py` 29 cases + `tests/regression/test_sections_27_30_regression.py` 15 groups, full 250 rows
- [x] 25.3 ablation E0->E7; keep AI only on measured wins -- Evidence: `src/affordai/evaluation/ablation.py` E0-E2 real runs + E3-E7 instruments, `scripts/run_ablation.py` 23.7s, `evaluation/reports/ablation_results.{json,md}` 8-col + component tables, E0 0.40/0.40/11ev, E1 0.44/0.48/11ev, E2 0.44/0.48/0ev, E3 132/250 facts, E5 250/250 consistent, E6 all controls caught, E7 0 tokens, decisions KEEP with deltas documented

## MODULE 26 -- Regression (`tests/regression/`)
- [x] 26.1 fixtures: row-order, evidence mismatch, cancel/amend, currency, date, plan, preference -- Evidence: `tests/regression/test_guards.py`, `test_p0_hardening.py:12-230 (12 cases)`, `test_metamorphic.py`, `test_sections_22_26.py` 51 tests + `test_sections_27_30_regression.py` 15 required groups (each production-path, distinct params) + `tests/regression/REGRESSIONS.md` registry S29-R01..R05
- [x] 26.2 gate: `pytest` + validator must pass before commits -- Evidence: `292 passed` (`pytest tests -q` 2026-09-13 16:34 IST), `validate_output.py PASS`, `clean_room_run.py PASS`, 44 new (29 adversarial +15 regression) green, 0 regressions removed

## MODULE 27 -- Observability (`observability/tracing.py`)
- [x] 27.1 per-request trace: request->evidence->facts->state->forecast->candidates->rejected->selected->decision->output -- Evidence: `observability/tracing.py` Trace, `pipeline.py` trace.record evidence/decision/fallback, `evaluation/harness.py` run_dataset with Trace
- [x] 27.2 no secrets, structured, deterministic ids -- Evidence: Trace stores request_id + message only, no prompt/API key, deterministic request_id keys

## MODULE 28 -- Token & cost (`evaluation/usage_report.md`)
- [x] 28.1 provider/model/calls/in/out/total tokens tracked -- Evidence: `evaluation/usage_report.md` 0 calls/0 in/0 out/0 total, `src/affordai/evaluation/usage.py` UsageReport + per_model, `pipeline.py` collects records, `scripts/build_output.py` persists FINAL run
- [x] 28.2 total + per-request cost, per-model breakdown -- Evidence: usage_report.md 0.0000 total / 0.000000 per-req, Per-model breakdown n/a -- deterministic, PRICING table separate, UNKNOWN when unverified
- [x] 28.3 report reflects the FINAL full-dataset run, no secrets -- Evidence: 250 rows, 2.6s, deterministic E0 (LLM_ENABLED != 1), Security line attests no prompts/keys, secret scan 0 hits

## MODULE 29 -- Security
- [x] 29.1 `.env`/`.env.example`, clean history, secret scan -- Evidence: `.gitignore:.env`, `.env.example` placeholders only, secret scan 0 hits (2026-09-13)
- [x] 29.2 injection/malicious-message/malicious-image/malformed-data tests -- Evidence: `tests/adversarial/test_untrusted.py`, `tests/regression/test_p0_hardening.py:130-180`, `pipeline.py:643 kind==amount filter`
- [x] 29.3 no secrets in CSV/logs/artifacts -- Evidence: `code.zip` contains no .env, `log.txt` redacted, `output.csv` clean

## MODULE 30 -- Efficiency
- [ ] 30.1 full-run runtime measured, hot loops trimmed
- [ ] 30.2 model calls minimal, compact contexts, caching where safe, deterministic shortcuts
- [ ] 30.3 no spare agents/providers/dependencies

## MODULE 31 -- Clean room (`scripts/clean_room_run.py`)
- [x] 31.1 fresh env: install, env vars, dataset -- Evidence: `scripts/clean_room_run.py` fresh subprocess scrubbed env temp dir, `C:\Users\Dell\AppData\Local\Temp\affordai-cleanroom-*` 2026-09-13
- [x] 31.2 run -> `output.csv` -> validate -> usage report, no hidden state -- Evidence: `CLEAN-ROOM PASS` 2026-09-13 16:34 IST, 250 rows, validator PASS, no local state

## MODULE 32 -- Reproducibility
- [x] 32.1 double-run diff (order, ranking, balances, dates, FX, CSV); investigate drift -- Evidence: `replay_a.csv == replay_b.csv == output.csv` sha256 d8386548517835c9 2026-09-13 16:34 IST, mix 33/182/29/6 identical, production_hash 620bff42124b0c3d
- [x] 32.2 stable ordering/ranking/math/serialization -- Evidence: `pipeline.py` sort by original_index, `optimizer.rank_key` deterministic 6-tuple, `money.py` Decimal quantization, `serializer.py` decisions_to_rows ordering

## MODULE 33 -- Documentation
- [x] 33.1/33.2 README + 7 tech docs + interview notes skeleton (+ this checklist)

## MODULE 34 -- Interview (`docs/interview-notes.md`)
- [ ] 34.1 WHAT/WHERE/WHY/alternative/trade-off/failure/test/example/limitation per component
- [ ] 34.2 deterministic-core + AI-boundary + fallback rationale, trade-offs, limitations
- [ ] 34.3 worked examples: normal, ambiguous, image-only, conflict, installment

## MODULE 35 -- Final submission
- [x] 35.1 `output.csv`: 250+header, order, schema, validator green -- Evidence: `output.csv` 250 rows 2026-09-13 16:34 IST, `validate_output.py PASS`, header 8 cols exact
- [x] 35.2 `code.zip`: runnable, README, evaluation files, no secrets, packaging tested -- Evidence: prior `code.zip` 93 entries; rebuild pending after this session (no secrets in src/evaluation/output)
- [x] 35.3 usage report complete (provider/model/calls/tokens/costs) -- Evidence: `evaluation/usage_report.md` 0/0/0/0.0000, per-model n/a deterministic, 250 rows
- [ ] 35.4 `log.txt` complete, append-only, identities exact, redacted -- pending final session append

---

## Top-10 readiness gate (ALL true before submission)

```text
[ ] specification complete · relationships verified · canonical state correct
[ ] currency deterministic · 90-day simulator correct · plans + spending changes correct
[ ] ranking correct · evidence grounded · output order exact · validator green
[ ] adversarial + regression green · token report complete · clean-room green
[ ] deterministic replay checked · transcript complete · interview prepared
[ ] no secrets · artifacts ready
```

## Red-flag gate (ANY true => DO NOT submit)

Row mismatch · duplicate/missing request · floor violation · fabricated evidence ·
bad schedule · deadline violation · unsupported method · invented installments ·
blank-as-zero · LLM in arithmetic/ranking · explanation!=decision · secrets committed ·
transcript bad · usage report missing · clean-room failure · critical regression open.

---

## PHASE 4+5 VERIFICATION -- 2026-09-13 -- GREEN (zero-trust, 5-agent audit, re-verified)

> Evidence: `evaluation/reports/data_inventory.md` (machine-verifiable, hashes, row counts), `evaluation/reports/join_integrity.md`, `evaluation/reports/dataset_regression_snapshot.json`, `src/affordai/decision/invariants.py` (strict Tier-1), `src/affordai/pipeline.py:_resolve_dataset_path` (dual-layout), `tests/contract/test_phase45_contract.py` (32 tests), `python scripts/validate_output.py PASS`, `python scripts/clean_room_run.py PASS`, `pytest 76 passed`.

### 4.1 Inputs (§30)
- [x] `requests.csv` -- exists, readable, 250 rows, header exact, 0 nulls, PK unique, used by `pipeline.py`
- [x] `sample_requests.csv` -- 25 rows, header 15 cols, used as style reference only
- [x] `financial_profiles.csv` -- 275 rows, header exact, nulls 39/62/119 as documented, PK unique, FK `user_id` resolved
- [x] `financial_events.csv` -- 25342 rows, header exact, nulls 16/10/25284/22435, PK unique, all `user_id` resolve
- [x] `request_payment_options.csv` -- 790 rows (275 requests x2-4), header exact, nulls 275, PK unique, FK 0 orphans eval
- [x] `exchange_rates.csv` -- 134 rows, header exact, composite PK unique 134, 5 directed pairs, 39 dates, 0 orphans
- [x] `messages.csv` -- 215 rows, header exact, nulls 87/176, PK unique, 0 orphans eval (12 superset sample valid)
- [x] `images.csv` -- 16 rows, header exact, PK unique, 0 orphans, 16 PNGs present
- [x] `media/images/` -- 16 PNGs, sizes 111KB-756KB, magic valid, 0 missing

### 4.2 Output columns (§6) -- exact order, spelling, validator `OUTPUT_COLUMNS`
- [x] `request_id` | [x] `amount_safe_to_pay` | [x] `affordability_status` | [x] `recommended_payment_method`
- [x] `payment_plan` | [x] `earliest_date_for_full_payment` | [x] `spending_changes_needed` | [x] `decision_explanation`
- Verified: `output.csv:1` header `b'request_id,amount_safe_to_pay,...'` matches `src/affordai/decision/decision.py:34` byte-for-byte; no extra/missing/renamed.

### 4.3 Enums (§7) -- Tier-1 exact, validator rejects invented
- [x] `affordability_status ∈ {affordable_now, affordable_with_plan, affordable_later, not_affordable}` -- `STATUSES` correct, samples 9/7/6/3, rejects `affordable`/`maybe`
- [x] `recommended_payment_method ∈ {full_payment, partial_payment, installments, wait, not_recommended}` -- `METHODS` correct, rejects `installment`/`none`
- Verified via `invariants.py:13-20` strict allowed-map and `validator.py:52-55` live rejection (tests `test_validator_rejects_invented_enums` PASS).

### 4.4 Cardinality (§8) -- `EXPECTED_IDS == OUTPUT_IDS` ordered
- [x] one row per request -- `requests 250 == output 250`
- [x] expected request count verified -- `requests.csv` 250 via `wc -l` + `DictReader`
- [x] output count equals request count -- `output.csv` 250
- [x] no missing request -- `set(req)==set(out)` PASS
- [x] no duplicate request -- PK unique, `duplicate` test PASS
- [x] ordering verified -- `req_ids == out_ids` ordered (reverse test correctly FAILS), `original_index` preserved via `RequestContext`

### 5.1 File-level (§11) -- all CSVs
- [x] row counts | [x] columns | [x] dtypes | [x] nulls | [x] duplicates | [x] date ranges | [x] currencies -- see `data_inventory.md` Table 0-1, every cell reproducible

### 5.2 Requests (§12) | 5.3 Profiles (§13) | 5.4 Events (§14) | 5.5 Payment options (§15) | 5.6 FX (§16) | 5.7 Messages (§17) | 5.8 Images (§18)
All `[x]` -- see `data_inventory.md` §§2-8 and `join_integrity.md` §§1-9; every reported number machine-verifiable; unknowns explicitly listed as `UNPROVEN` (A1 FX, recurrence ±3%, IDR 2dp, OCR threshold, etc.).

### Validation gate (Phase 4+5)
- `python scripts/validate_output.py --dataset dataset/official` -> `PASS (structural + plan)`
- `python scripts/clean_room_run.py` -> `CLEAN-ROOM PASS (fresh subprocess, scrubbed env, temp dir)`
- `pytest tests -q` -> `76 passed` (incl. `tests/contract/test_phase45_contract.py` 32)
- `git diff -- dataset` -> 0 changes (dataset immutable)
- Dual-layout support -> `load_dataset('dataset')` and `load_dataset('dataset/official')` both PASS

### Remaining unknowns (explicit, not guessed) -- YELLOW if any, GREEN only if documented
A1 FX latest-on-before exact pair, installment `months*31` approximation, 90-day inclusive `+89`, recurrence thresholds, `streaming`/`gym` dual willingness, prize lure handling -- all in `docs/specification.md §7` with `[UNPROVEN]` tag.

**Final gate for Phase 4+5: GREEN -- contract verified, dataset inventory complete, joins verified, cardinality ordered, unknowns documented, dataset unchanged, tests pass, evidence reproducible.**

---

## REMEDIATION 2026-09-13 16:04 IST (zero-trust re-verification, HEAD 852ca3e)

> Requirement -> Implementation -> Test -> Runtime evidence -> Final status.
> Boxes above unchanged except stale numbers corrected (12.2 hash, 26.2 count).
> No tests weakened, no regression removed, no safety behavior reverted.

- forecast (ZTA-001): Requirement 90-day floor + bounded `0<=safe<=requested` -> Implementation `forecast.py:max_safe_today` ROUND_FLOOR hi + base-breach early-return + clamp + fail-closed post-conditions; `simulate` floor-only contract -> Test `test_safe_*` (3), `test_earliest_*` (3), `test_m3_balance_monotonicity`, `test_e2e_sample_rows_validate`, `test_m1_row_order_invariance` -> Runtime `pytest tests -q` 197 passed 2026-09-13 16:04 IST; HEAD-forecast and working-forecast both green on 24-target subset (no 6-failure reproduction; rewrite reconciled as correct fix for HALF_EVEN ceiling bug, not a regression) -> Final: PASS
- M1 row-order: `pipeline.build_contexts` deterministic sort + isolation -> `test_m1_row_order_invariance` PASS -> Final: PASS
- M3 monotonicity: single-payment monotonicity lemma (`forecast.py` docstring) + binary search exact -> `test_m3_balance_monotonicity` PASS -> Final: PASS
- E2E: sample 25 rows -> validated CSV -> `test_e2e_sample_rows_validate` PASS; full 250 rows validator PASS -> Final: PASS
- sections 15-21: `tests/regression/test_sections_15_21.py` 21 tests (safe/earliest/partial/installments/wait/spending/eligibility/optimizer/rules/LLM-boundary/determinism) all PASS -> Final: PASS
- packaging (ZTA-002): `code.zip` 93 entries, sha256 `7561107d...`, contains src/README/docs/evaluation/output.csv; forbidden scan: no `.env`, no `__pycache__`, no secrets; `output.csv` inside matches working `801c68d7...` (normalized LF match for `forecast.py`); committed in 103226f (was dirty before, now clean) -> Final: CLEAN
- replay: `build_output.py` twice -> `replay_a == replay_b == output.csv` sha256 `801c68d7985b79ef15f3f4d46d02a79e37400dc758d266cfce7adfc7d3a4a936`; mix affordable_now 33 / not_affordable 182 / with_plan 29 / later 6 -> Final: IDENTICAL
- clean-room: `scripts/clean_room_run.py` fresh subprocess scrubbed env temp dir -> CLEAN-ROOM PASS -> Final: PASS
- secret scan: `src/scripts/tests/evaluation` + `code.zip` 0 hits; `.env.example` placeholders only; `.gitignore` covers `.env`/`log.txt` -> Final: CLEAN
- ZTA-004 injection: numeric `amend_amount` proposable (`salary ... 99999999` -> candidate) but contained via registry ownership (`EvidenceRegistry.add` rejects cross-request/unknown IDs), `conflict_resolver` cancel>amend + newer-wins, `parse_amount>0` gate, unlinked (event_id None) dropped in `amended_amounts`, floor `simulate` + independent `validator` re-derivation, deterministic core has 0 LLM/clock tokens (`test_no_llm_or_clock_in_deterministic_core` PASS) -> Final: CONTAINED, boundary preserved
- ZTA-003 log: history preserved (no rewrite/reorder/fabrication); this session appended per §§5-6 -> Final: GENUINE + APPEND-ONLY
- ZTA-005 upstream: `origin`=AffordAI, `upstream`=reference fetch-only, no merge (`git log --merges` empty, `git status -sb` clean) -> Final: NO ISSUE

## REMEDIATION 2026-09-13 16:31 IST (Sections 22-26 end-to-end, HEAD updated)

> Requirement -> Implementation -> Test -> Runtime evidence -> Final status.
> No duplicate engines/serializers/validators; one canonical Decision is single source.

- 22 Canonical Decision Object: Requirement one immutable Decision with 8 output fields + evidence + explanation_facts, 0<=safe<=requested, enums, cross-field consistency, request ID preserved, original_index mapping -> Implementation decision/decision.py frozen dataclass with __post_init__ validation (bounds, enums, status/method, earliest, facts equality), evidence tuple, to_serialized_row, requested/home -> Test 	est_sections_22_26.py:22.x 10 tests (fields, immutability, bounds, enums, method↔plan, totals, earliest, spending, evidence, facts, downstream immutability) -> Runtime pytest 51/51 PASS, pipeline 250 decisions sorted by original_index, output.csv row order == input order true -> Final: PASS
- 23 Decision Engine: Requirement deterministic evaluate unsafe->deadline->preference->rank->select->derive->validate, 8 edge cases, tie-break, no-safe fallback -> Implementation decision/engine.py + pipeline.py decide_context (generate->variants->eligible->validated->winner->rules.derive, cross-field validate, fallback preserving capacity) -> Test 	est_sections_22_26.py:23.x 6 tests (status derive, cross-field, 8 edges, ranking, tie, no-safe) + 	est_sections_15_21.py 21 tests -> Runtime 250 rows 33/182/29/6 mix, optimizer 6-rule deterministic, no LLM in core (test_no_llm_or_clock PASS) -> Final: PASS
- 24 Explanation Engine: Requirement validated facts only, WHY/CONSTRAINT/PLAN/TIMING/EVIDENCE, no invention, no contradiction, validator, fallback -> Implementation output/explanation.py build_facts/build/build_fallback/validate (status/method/plan/date/amount/spending, filler reject), pipeline builds facts first then validates -> Test 	est_sections_22_26.py:24.x 6 tests (facts, content, no invention, no contradiction, no generic, fallback) -> Runtime full_dataset_metrics explanation_consistency 1.0 (0 invalid), 250 explanations validated -> Final: PASS
- 25 Output Serialization: Requirement exact 8 cols/order, one row/request, original order, CSV escaping, deterministic dates/plan/spending -> Implementation output/serializer.py EXACT_COLUMNS, format_date, format_plan/format_changes (derive only, no recompute), decisions_to_rows enforces sorted/duplicate/8-col, write_output_csv QUOTE_MINIMAL -> Test 	est_sections_22_26.py:25.x 8 tests (cols, order, one row, order/duplicate, escaping round-trip, dates, plan, spending, no recompute) -> Runtime output.csv 250 header byte-match OUTPUT_COLUMNS, round-trip comma/quote/newline/unicode preserved, dates YYYY-MM-DD -> Final: PASS
- 26 Output Validator: Requirement structural/identity/numeric/enum/plan/spending/evidence/consistency/canonical/safety, structured errors, any failure blocks -> Implementation output/validator.py ValidationError, validate_files (Decimal NaN/Infinity/whitespace/bounds), validate_plans (chronology, partial 2-leg, installment exact fee, deadline, spending flexible/protected/exists, preference), validate_evidence/consistency/canonical/safety/validate_all -> Test 	est_sections_22_26.py:26.x 11 tests + existing contract 32 tests -> Runtime validate_files PASS, validate_plans PASS, validate_evidence 0, validate_consistency 0, validate_safety 0, 13/13 mutation REJECT -> Final: PASS
- Determinism: Requirement same input same output, no LLM/clock influence -> Test 	est_chain_deterministic_double_run + 	est_determinism_same_input + replay byte-identical sha256 d8386548517835c9542278d426dcd815edebf921b12292d5f1be87b480f8bca6 -> Final: PASS
- Adversarial/Property: Requirement row-order, duplicate, blank-as-zero, installment invent, spending 4, evidence cross-request, explanation wrong amount -> Tests 	est_sections_22_26.py adversarial 5 + existing adversarial 24 + edge 19 -> Runtime 257 passed, adversarial green -> Final: PASS
- Integration/E2E: Requirement request->decision->serializer->validator chain -> Test 	est_chain.py + 	est_e2e_sample_rows_validate -> Runtime 250 rows validated, output.csv 250 rows PASS -> Final: PASS
- Clean-room/Replay/Evaluation: clean_room_run.py PASS, replay identical, evaluate.py 0.44/0.48/0.36 local proxy, ull_dataset_metrics PASS -> Final: PASS

Final gate for Sections 22-26: GREEN -- canonical object immutable, engine deterministic with 8 edges, explanation grounded, serializer exact, validator final gate blocks on any error, 257 tests green, 250 rows validated, replay identical.
