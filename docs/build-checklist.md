# Build Checklist — Modules 0–35 (completion gate)

Status per item: `[ ]` not started · `[~]` partial · `[x]` complete · `[!]` blocked/risky · `[-]` n/a.
Referenced by `AGENTS.md` §§27–27b, 30. Update as work lands.

## MODULE 0 — Repository & governance
- [x] 0.1 repo init, `origin`=AffordAI, `upstream`=official-ref, branch/worktree known
- [x] 0.2 `.gitignore` (.env, log.txt, local dirs), no secrets, meaningful commits, upstream never merged
- [~] 0.3 transcript: root `log.txt`, append-only, session-start + per-turn, exact `tool=`, redaction, shared log
  (logging began 2026-09-13; earlier turns predate the contract — noted in log)

## MODULE 1 — Specification
- [~] 1.1 core spec (objective, I/O, enums, financial/temporal/evidence/conflict/preference rules, prohibitions)
  (draft exists but not Tier-1 re-verified — honest ~ per zero-trust)
- [~] 1.2 decision matrix (states, methods, partial/installment/spending/deadline/tie-break rules)
  (draft exists but not code-proven — honest ~)
- [~] 1.3 edge semantics (missing values, duplicates, cancels, amendments, settlement, unresolved conflicts,
  missing evidence/FX — FX fallback A1 set; rest pending engine)

## MODULE 2 — Data ingestion (`src/affordai/ingestion/`)
- [x] 2.1 loaders: requests, profiles, events, payment options, FX, messages, images — Evidence: `ingestion/*.py` typed loaders, `pipeline.py:191-203 load_dataset` dual-layout
- [x] 2.2 schema validation: columns, types, nulls, unexpected values, row counts — Evidence: `ingestion/__init__.py require_decimal/parse_amount_safe`, `evaluation/reports/data_inventory.md`
- [x] 2.3 identity: `original_index`, `request_id`, `user_id`; no cross-request/user leaks — Evidence: `pipeline.py:393-412 _validate_request_identity`, `tests/contract/test_phase45_contract.py` PK unique

## MODULE 3 — Relationship / join engine
- [x] 3.1 joins: user→profile, request→user/options/messages, event→image — Evidence: `pipeline.py:233-390 build_contexts()` with deterministic sorting
- [x] 3.2 lifecycle: `linked_event_id`, `related_event_id`, amendments, duplicate detection — Evidence: `pipeline.py:206-230 _dedupe_by_key`, `build_contexts` orphan checks
- [x] 3.3 safety: missing refs, ownership, multiplicity, no duplicate joins — Evidence: `pipeline.py:414-557 _validate_fk_integrity`, `JoinIntegrityIssue`, `tests/contract/join_integrity.md`

## MODULE 4 — Canonical request context (`pipeline.py: RequestContext`)
- [x] 4.1 object carries index/ids/request/profile/events/messages/images/options/evidence — Evidence: `pipeline.py:41-95 RequestContext` with join_issues
- [x] 4.2 immutable identity, deterministic ordering — Evidence: `pipeline.py:60-95 validate_identity/validate_relationships`, events (settlement_date,event_id), messages (sent_at,message_id) sorted, isolation via dict copy

## MODULE 5 — Evidence system (`evidence/evidence_registry.py`)
- [x] 5.1 provenance fields (source type/id, request/user/event/message/image, raw/normalized, method, confidence) — Evidence: `evidence_registry.py:15-48 provenance()`, `pipeline.py:589-605 sent_at stamping` 
- [x] 5.2 validation: IDs exist, correct owner, supports claim, no fabrication — Evidence: `evidence_registry.py:76-130 add() with valid_* IDs + rejected trace`, `tests/regression/test_p0_hardening.py:210-230`, `tests/adversarial/test_untrusted.py:59-69` PASS

## MODULE 6 — Message intelligence
- [x] 6.1 detect: cancel/settle/amend/delay/confirm/amount-change/date-change/preference — Evidence: `message_interpreter.py:15-29 _PATTERNS+_PREF_PATTERNS`, `tests/regression/test_p0_hardening.py:55-90,130` PASS
- [x] 6.2 safety: injection resistance, irrelevant/malformed handling, provenance — Evidence: `message_interpreter.py:1-7 zero-trust`, `tests/regression/test_p0_hardening.py:130-180`, `tests/adversarial/test_untrusted.py:23-40` PASS
- [x] 6.3 AI: bounded prompt, structured schema, validation, fallback, token tracking — Evidence: `evidence/llm_adapter.py:70-105 _validate_proposal`, `pipeline.py:610-627 min_confidence gate`, `evaluation/usage_report.md` E0 0-calls

## MODULE 7 — Image intelligence
- [x] 7.1 resolution: id mapping, file exists, linkage, relevance filter — Evidence: `evidence/image_interpreter.py:20-38`, `pipeline.py:628-634 selective trigger`, `tests/contract/test_phase45_contract.py:319-327` 16↔16 bijection
- [~] 7.2 extraction: amount, currency, context, confidence, provenance — Deterministic UNKNOWN-safe (E0 stub); `llm_adapter.py:108-122 no-backend`, `pipeline.py:643-674 amount_unknown_evidence` — full vision deferred per spec, blank≠zero enforced
- [x] 7.3 failures: blank/missing/unreadable/irrelevant/malicious-image handling (blank≠zero, 16↔16 verified) — Evidence: `finance/money.py:39-57 blank→None never 0`, `pipeline.py:643 filter kind==amount`, `tests/regression/test_p0_hardening.py:100-150`, `tests/unit/test_engine_units.py:52-64` PASS

## MODULE 8 — Conflict resolution (`evidence/conflict_resolver.py`)
- [x] 8.1 precedence: cancel/settle/amend → newer same-source → settled → safer; deterministic; AI can't override — Evidence: `conflict_resolver.py:18-85 _EXPLICIT_ORDER+_method_rank+stable 3-pass sort`, `detect_conflicts()` audit, `pipeline.py:598 sent_at` stamping
- [x] 8.2 regression fixtures — Evidence: `tests/regression/test_p0_hardening.py:12-80 (8 cases)`, `tests/unit/test_engine_units.py:187-190` PASS

## MODULE 9 — Currency engine (`finance/currency.py`)
- [x] 9.1 same/foreign conversion, dated rate, direction, home-currency output (A1: latest row ≤ settlement) — Evidence: `currency.py:RateTable.get_rate/convert_to_home`, `tests/unit/test_sections_12_14_units.py` (12 tests) PASS 2026-09-13
- [x] 9.2 failures: missing rate/date-mismatch/unsupported pair/invalid amount (fail-closed + log) — Evidence: `MissingRateError/UnsupportedCurrencyError/DuplicateRateError`, `ConversionTrace.reason`, `load_skipped`, `tests/edge_cases + adversarial` (network-disabled) PASS

## MODULE 10 — Temporal engine (`finance/temporal.py` + `finance/timeline.py`)
- [x] 10.1 request/event/settlement/income/recurring/payment/completion dates, 90-day horizon — Evidence: `temporal.py` single-source WINDOW_DAYS=90, `forecast_end=+89`, `timeline.py`/`forecast.py` consume it, `tests/unit` (5 tests) PASS
- [x] 10.2 edges: same-day, boundary, deadline-day, 90-day boundary, recurrence anomalies — Evidence: `flow_sort_key`, `meets_deadline(<=)`, `clamp_month_day`, `generate_monthly/interval_occurrences`, `tests/edge_cases` (9 tests) PASS

## MODULE 11 — Financial state engine (`finance/state.py`)
- [x] 11.1 balance, minimum, essentials, flexible, recurring income, obligations, valid settled events — Evidence: `state.build` validates opening/minimum/requested/home/dates/flows + provenance, `tests/unit` (4 tests) PASS
- [x] 11.2 pending debit (reserve) vs pending credit (ignore), failed/cancelled/duplicate/unrealized excluded,
  confirmed salary on settlement date only — Evidence: `timeline.build_flows` inclusion rules + `state.build` duplicate/out-of-window gate, `tests/edge_cases + integration` (12 tests) PASS; full output.csv byte-identical before/after refactor, double-run identical, clean-room PASS 2026-09-13

## MODULE 12 — 90-day forecast (`finance/forecast.py`)
- [ ] 12.1 daily ledger: opening, inflows, essentials, recurring, existing + candidate payments, closing
- [ ] 12.2 invariant `closing >= minimum` every day; no double-counting; deterministic

## MODULE 13 — Payment-plan engine (`finance/payment_plans.py`)
- [ ] 13.1 candidates: full / partial / installments / wait / spending-change variants / not_recommended
- [ ] 13.2 each: safety → deadline → preference → ranking

## MODULE 14 — Amount safe to pay
- [ ] 14.1 max safe today, before optional changes, bounded, deterministic search
- [ ] 14.2 boundaries: 0, full, exact edge, ±edge

## MODULE 15 — Earliest full-payment date
- [ ] 15.1 scan from `request_date`; first safe single-payment date; empty if never; preference-independent
- [ ] 15.2 safety + deadline validation

## MODULE 16 — Partial payment
- [ ] 16.1 eligible: allows-partial, user accepts, `0 < safe < requested`, `earliest <= deadline`
- [ ] 16.2 exactly 2 payments (`safe` + remainder = requested), safe, on time

## MODULE 17 — Installments
- [ ] 17.1 exact match: option id, count, dates, amounts, fees
- [ ] 17.2 user accepts installments, month-limit ok, safe, on time

## MODULE 18 — Spending changes (`finance/spending_changes.py`)
- [x] 18.1 flexible-only, protected kept, ≤3, syntax valid, stop/reduce exclusive — Evidence: `spending_changes.py:32-60 candidate_targets()` protected guard, STOP_OK/REDUCE_OK, `tests/regression/test_p0_hardening.py:84-98` PASS
- [x] 18.2 change flips plan safe, deadline holds, no gratuitous changes — Evidence: `spending_changes.py:72-106 find_variants()` simulate+deadline gate, `validator.py:207-234` ≤3 syntax check

## MODULE 19 — Method eligibility (`decision/eligibility.py`)
- [ ] 19.1 filter by accepted/excluded methods, installment + partial preferences
- [ ] 19.2 selected plan is safe + eligible + correctly ranked

## MODULE 20 — Ranker (`finance/optimizer.py`)
- [ ] 20.1 deadline → no-changes → min total → earlier start → fewer payments → lowest option id
- [ ] 20.2 tie tests incl. final option-id break

## MODULE 21 — Decision (`decision/decision.py`)
- [ ] 21.1 canonical `Decision` carries all 8 fields + evidence + explanation facts
- [ ] 21.2 status↔method↔plan↔dates↔changes↔explanation consistent

## MODULE 22 — Output (`output/serializer.py`, `validator.py`, `scripts/validate_output.py`)
- [ ] 22.1 exact columns/order/count/request order
- [~] 22.2 structural validator live; financial/plan/date/evidence/consistency layers pending engine

## MODULE 23 — Explanation (`output/explanation.py`)
- [ ] 23.1 facts ⊆ validated decision facts; amounts/dates/evidence match; nothing invented
- [ ] 23.2 concise, specific, decision-consistent

## MODULE 24 — AI layer
- [ ] 24.1/24.2/24.3 message/image/explanation prompts bounded, schema-validated, fallback + usage tracked;
  explanation receives validated facts only

## MODULE 25 — Evaluation (`evaluation/`, `scripts/evaluate.py`)
- [ ] 25.1 local proxies: structural/financial/decision/plan/evidence/explanation/robustness (NOT official score)
- [ ] 25.2 sample/edge/adversarial/regression/full-dataset suites
- [ ] 25.3 ablation E0→E7; keep AI only on measured wins

## MODULE 26 — Regression (`tests/regression/`)
- [x] 26.1 fixtures: row-order, evidence mismatch, cancel/amend, currency, date, plan, preference — Evidence: `tests/regression/test_guards.py`, `test_p0_hardening.py:12-230 (12 cases)`, `test_metamorphic.py`
- [x] 26.2 gate: `pytest` + validator must pass before commits — Evidence: `88 passed`, `validate_output.py PASS`, `clean_room_run.py PASS` (2026-09-13 15:00 UTC)

## MODULE 27 — Observability (`observability/tracing.py`)
- [ ] 27.1 per-request trace: request→evidence→facts→state→forecast→candidates→rejected→selected→decision→output
- [ ] 27.2 no secrets, structured, deterministic ids

## MODULE 28 — Token & cost (`evaluation/usage_report.md`)
- [ ] 28.1 provider/model/calls/in/out/total tokens tracked
- [ ] 28.2 total + per-request cost, per-model breakdown
- [ ] 28.3 report reflects the FINAL full-dataset run, no secrets

## MODULE 29 — Security
- [x] 29.1 `.env`/`.env.example`, clean history, secret scan — Evidence: `.gitignore:.env`, `.env.example` placeholders only, secret scan 0 hits (2026-09-13)
- [x] 29.2 injection/malicious-message/malicious-image/malformed-data tests — Evidence: `tests/adversarial/test_untrusted.py`, `tests/regression/test_p0_hardening.py:130-180`, `pipeline.py:643 kind==amount filter`
- [x] 29.3 no secrets in CSV/logs/artifacts — Evidence: `code.zip` contains no .env, `log.txt` redacted, `output.csv` clean

## MODULE 30 — Efficiency
- [ ] 30.1 full-run runtime measured, hot loops trimmed
- [ ] 30.2 model calls minimal, compact contexts, caching where safe, deterministic shortcuts
- [ ] 30.3 no spare agents/providers/dependencies

## MODULE 31 — Clean room (`scripts/clean_room_run.py`)
- [ ] 31.1 fresh env: install, env vars, dataset
- [ ] 31.2 run → `output.csv` → validate → usage report, no hidden state

## MODULE 32 — Reproducibility
- [ ] 32.1 double-run diff (order, ranking, balances, dates, FX, CSV); investigate drift
- [ ] 32.2 stable ordering/ranking/math/serialization

## MODULE 33 — Documentation
- [x] 33.1/33.2 README + 7 tech docs + interview notes skeleton (+ this checklist)

## MODULE 34 — Interview (`docs/interview-notes.md`)
- [ ] 34.1 WHAT/WHERE/WHY/alternative/trade-off/failure/test/example/limitation per component
- [ ] 34.2 deterministic-core + AI-boundary + fallback rationale, trade-offs, limitations
- [ ] 34.3 worked examples: normal, ambiguous, image-only, conflict, installment

## MODULE 35 — Final submission
- [ ] 35.1 `output.csv`: 250+header, order, schema, validator green
- [ ] 35.2 `code.zip`: runnable, README, evaluation files, no secrets, packaging tested
- [ ] 35.3 usage report complete (provider/model/calls/tokens/costs)
- [ ] 35.4 `log.txt` complete, append-only, identities exact, redacted

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

## Red-flag gate (ANY true ⇒ DO NOT submit)

Row mismatch · duplicate/missing request · floor violation · fabricated evidence ·
bad schedule · deadline violation · unsupported method · invented installments ·
blank-as-zero · LLM in arithmetic/ranking · explanation≠decision · secrets committed ·
transcript bad · usage report missing · clean-room failure · critical regression open.

---

## PHASE 4+5 VERIFICATION — 2026-09-13 — GREEN (zero-trust, 5-agent audit, re-verified)

> Evidence: `evaluation/reports/data_inventory.md` (machine-verifiable, hashes, row counts), `evaluation/reports/join_integrity.md`, `evaluation/reports/dataset_regression_snapshot.json`, `src/affordai/decision/invariants.py` (strict Tier-1), `src/affordai/pipeline.py:_resolve_dataset_path` (dual-layout), `tests/contract/test_phase45_contract.py` (32 tests), `python scripts/validate_output.py PASS`, `python scripts/clean_room_run.py PASS`, `pytest 76 passed`.

### 4.1 Inputs (§30)
- [x] `requests.csv` — exists, readable, 250 rows, header exact, 0 nulls, PK unique, used by `pipeline.py`
- [x] `sample_requests.csv` — 25 rows, header 15 cols, used as style reference only
- [x] `financial_profiles.csv` — 275 rows, header exact, nulls 39/62/119 as documented, PK unique, FK `user_id` resolved
- [x] `financial_events.csv` — 25342 rows, header exact, nulls 16/10/25284/22435, PK unique, all `user_id` resolve
- [x] `request_payment_options.csv` — 790 rows (275 requests ×2–4), header exact, nulls 275, PK unique, FK 0 orphans eval
- [x] `exchange_rates.csv` — 134 rows, header exact, composite PK unique 134, 5 directed pairs, 39 dates, 0 orphans
- [x] `messages.csv` — 215 rows, header exact, nulls 87/176, PK unique, 0 orphans eval (12 superset sample valid)
- [x] `images.csv` — 16 rows, header exact, PK unique, 0 orphans, 16 PNGs present
- [x] `media/images/` — 16 PNGs, sizes 111KB–756KB, magic valid, 0 missing

### 4.2 Output columns (§6) — exact order, spelling, validator `OUTPUT_COLUMNS`
- [x] `request_id` | [x] `amount_safe_to_pay` | [x] `affordability_status` | [x] `recommended_payment_method`
- [x] `payment_plan` | [x] `earliest_date_for_full_payment` | [x] `spending_changes_needed` | [x] `decision_explanation`
- Verified: `output.csv:1` header `b'request_id,amount_safe_to_pay,...'` matches `src/affordai/decision/decision.py:34` byte-for-byte; no extra/missing/renamed.

### 4.3 Enums (§7) — Tier-1 exact, validator rejects invented
- [x] `affordability_status ∈ {affordable_now, affordable_with_plan, affordable_later, not_affordable}` — `STATUSES` correct, samples 9/7/6/3, rejects `affordable`/`maybe`
- [x] `recommended_payment_method ∈ {full_payment, partial_payment, installments, wait, not_recommended}` — `METHODS` correct, rejects `installment`/`none`
- Verified via `invariants.py:13-20` strict allowed-map and `validator.py:52-55` live rejection (tests `test_validator_rejects_invented_enums` PASS).

### 4.4 Cardinality (§8) — `EXPECTED_IDS == OUTPUT_IDS` ordered
- [x] one row per request — `requests 250 == output 250`
- [x] expected request count verified — `requests.csv` 250 via `wc -l` + `DictReader`
- [x] output count equals request count — `output.csv` 250
- [x] no missing request — `set(req)==set(out)` PASS
- [x] no duplicate request — PK unique, `duplicate` test PASS
- [x] ordering verified — `req_ids == out_ids` ordered (reverse test correctly FAILS), `original_index` preserved via `RequestContext`

### 5.1 File-level (§11) — all CSVs
- [x] row counts | [x] columns | [x] dtypes | [x] nulls | [x] duplicates | [x] date ranges | [x] currencies — see `data_inventory.md` Table 0–1, every cell reproducible

### 5.2 Requests (§12) | 5.3 Profiles (§13) | 5.4 Events (§14) | 5.5 Payment options (§15) | 5.6 FX (§16) | 5.7 Messages (§17) | 5.8 Images (§18)
All `[x]` — see `data_inventory.md` §§2–8 and `join_integrity.md` §§1–9; every reported number machine-verifiable; unknowns explicitly listed as `UNPROVEN` (A1 FX, recurrence ±3%, IDR 2dp, OCR threshold, etc.).

### Validation gate (Phase 4+5)
- `python scripts/validate_output.py --dataset dataset/official` → `PASS (structural + plan)`
- `python scripts/clean_room_run.py` → `CLEAN-ROOM PASS (fresh subprocess, scrubbed env, temp dir)`
- `pytest tests -q` → `76 passed` (incl. `tests/contract/test_phase45_contract.py` 32)
- `git diff -- dataset` → 0 changes (dataset immutable)
- Dual-layout support → `load_dataset('dataset')` and `load_dataset('dataset/official')` both PASS

### Remaining unknowns (explicit, not guessed) — YELLOW if any, GREEN only if documented
A1 FX latest-on-before exact pair, installment `months*31` approximation, 90-day inclusive `+89`, recurrence thresholds, `streaming`/`gym` dual willingness, prize lure handling — all in `docs/specification.md §7` with `[UNPROVEN]` tag.

**Final gate for Phase 4+5: GREEN — contract verified, dataset inventory complete, joins verified, cardinality ordered, unknowns documented, dataset unchanged, tests pass, evidence reproducible.**
