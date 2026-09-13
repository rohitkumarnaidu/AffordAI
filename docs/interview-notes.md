# Interview Notes -- AffordAI (living defense log)

> 60s walkthrough: request -> resolve data (ingestion) -> interpret evidence (messages/images) -> financial state -> 90-day forecast simulation -> generate candidates -> validate safety/deadline/preference -> rank deterministically -> Decision -> grounded explanation -> validator -> CSV. Every amount is Decimal, every date is YYYY-MM-DD, every plan is re-derived.

## System walkthrough (60s)

```
Request (requests.csv: request_id/user_id/request_date/desired_completion_date/requested_amount/allows_partial)
  -> resolve data (pipeline.build_contexts: join user->profile/events/messages/images/options, index by user/request, deduplicate PK, record JoinIntegrityIssue)
  -> interpret evidence (evidence/message_interpreter.interpret: typed facts only; image_interpreter.resolve_images_for_event: 16 linked, blank!=0)
  -> financial state (finance/state.build: opening/minimum/requested, flows from timeline.build_flows)
  -> simulate 90d (finance/forecast.simulate: daily ledger closing>=minimum every day; max_safe_today, earliest_full_date)
  -> generate candidates (finance/payment_plans.generate: full/partial/installments/wait, spending_changes.find_variants flex-only <=3)
  -> validate (filter_candidates preference/deadline/term + simulate safety) -> rank (finance/optimizer.rank_key: deadline->no-changes->min total->earlier start->fewer payments->lowest option_id)
  -> Decision (decision/decision.py: 8 columns, Decimal safe, invariants) -> explanation (output/explanation.build: facts subset, validated)
  -> validate (output/validator.validate_files/plans/evidence/consistency/safety) -> CSV (output/serializer.write_output_csv)
```

Files: `src/affordai/pipeline.py` orchestrates; `ingestion/` resolves; `evidence/` interprets; `finance/` computes; `decision/` decides+guards; `output/` explains+serializes+validates; `evaluation/` measures.

## Per-Component Deep Dive

### Deterministic Financial Core (pipeline.py:decide_context)

* **WHAT:** Single authoritative path `decide_context` -> `_collect_evidence` -> `build_flows` -> `build_state` -> `max_safe_today`/`earliest_full_date` -> `generate` -> `filter_candidates` -> `simulate` -> `select` -> `Decision`.
* **WHERE:** `src/affordai/pipeline.py:decide_context` (680-850), `run` 1023-1080
* **WHY:** Exact safe decisions require auditable, reproducible arithmetic; LLM never touches arithmetic.
* **INPUTS:** `RequestContext` (original_index/request_id/user_id + request/profile/events/messages/images/options), `tables` (rates)
* **OUTPUTS:** `Decision` (8 fields + evidence tuple)
* **AUTHORITY:** All financial facts (balances, flows, safe, earliest) from deterministic code; LLM only proposes typed facts via `llm_adapter.propose_facts` (validated-or-dropped, 0 in E0)
* **FAILURE MODES:** Unexpected per-request exception -> `_decide_safe` fallback `not_affordable/none/0` preserving safe/earliest when derivable; never crashes batch
* **TEST COVERAGE:** `tests/contract/test_s68_integrity.py` identity, `tests/regression/test_sections_15_21.py` safe/earliest/partial/installments, `tests/e2e/test_pipeline_e2e.py` full chain

### Forecast & Balance Simulation (finance/forecast.py, finance/state.py, finance/timeline.py)

* **WHAT:** Daily ledger 90 days inclusive (`temporal.forecast_end = request_date+89`), `simulate(state,payments,changes).ok` checks `closing_balance >= minimum` every day + deadline
* **WHERE:** `finance/forecast.py:simulate` (40-120), `max_safe_today` (binary search ROUND_FLOOR), `earliest_full_date` (forward scan), `finance/state.py:build` (opening/minimum/requested, daily_net), `finance/timeline.py:build_flows` (scheduled/settled future + message-confirmed salary)
* **WHY:** Central invariant: plan safe ONLY if floor holds every projected day and completes by `desired_completion_date`. Pending credits ignored, pending debits reserved, duplicate/failed/cancelled excluded, FX via `RateTable`
* **INPUTS:** `FinancialState`, candidate `payments: list[(date,Decimal)]`
* **OUTPUTS:** `SimulationResult(ok, reason, daily_closings)`, `safe: Decimal` (0<=safe<=requested), `earliest: date|None`
* **AUTHORITY:** Deterministic Decimal arithmetic, `ROUND_FLOOR` for safe, binary search monotonicity lemma
* **FAILURE MODES:** `MissingRateError` fail-closed (no foreign credit), empty window -> safe 0, breached baseline -> early-return
* **TEST COVERAGE:** `tests/regression/test_sections_15_21.py` safe bounds/monotone, earliest minimality, `tests/adversarial/test_sections_12_14_adversarial.py` window/boundary, `tests/edge_cases/test_boundaries.py` floor exact

### Decision Rules (decision/rules.py, decision/decision.py, decision/invariants.py)

* **WHAT:** `rules.derive(winner)` -> `(status,method)` mapping: `full->affordable_now`, `partial/installments+changes->affordable_with_plan`, `wait->affordable_later`, `None->not_affordable/not_recommended`
* **WHERE:** `decision/rules.py:derive`, `decision/decision.py` `Decision` dataclass (OUTPUT_COLUMNS order, frozen, __post_init__ checks 0<=safe<=requested + status/method/earliest consistency), `decision/invariants.py` `check_earliest_consistency`
* **WHY:** Status<->method<->plan<->earliest must be consistent per Tier-1 contract (decision-matrix A-E)
* **INPUTS:** `Candidate|None`
* **OUTPUTS:** `(affordability_status, recommended_payment_method)` enums strict
* **AUTHORITY:** Deterministic code; LLM never decides
* **FAILURE MODES:** Invariant violation -> `_fallback_decision` + `trace` record
* **TEST COVERAGE:** `tests/regression/test_sections_15_21.py:test_rules_derive_full_mapping`, `tests/regression/test_sections_22_26.py` invariants, `tests/unit/test_contract_invariants.py`

### Message Interpretation (evidence/message_interpreter.py, evidence/llm_adapter.py, evidence/message_income.py)

* **WHAT:** Deterministic regex `interpret(message)` emits typed facts only (`cancel/settle/confirm/delay/amend_amount/amend_date/preference`), never financial decisions. Salary confirmation via `message_income.confirmed_series` (employer+confirm semantics+salary keywords, deny-first)
* **WHERE:** `evidence/message_interpreter.py:interpret` (47-98), `_PATTERNS`/`_AMOUNT_RE`/`SALARY_RE`, `evidence/message_income.py:confirmed_series`, `evidence/llm_adapter.py:propose_facts` (bounded, schema-validated, 0 in E0)
* **WHY:** Messages are UNTRUSTED EVIDENCE; rule engine never reads raw text so `ignore minimum` cannot override floor
* **INPUTS:** single `message` dict (message_id/user_id/request_id/related_event_id/message_text/sent_at)
* **OUTPUTS:** `list[Evidence]` with provenance (source_type/message_id/request_id/user_id/event_id/raw/normalized/confidence=1.0/method=deterministic)
* **AUTHORITY:** Deterministic regex; LLM adapter only proposes typed facts (validated-or-dropped, confidence >=0.80, `needs_llm_for_messages` selective)
* **FAILURE MODES:** No pattern -> 0 facts (safe), payroll ref `EMP-0001` never parses as amount, injection `0` parsed but dropped by `parse_amount>0` + event_id gate + floor re-simulation
* **TEST COVERAGE:** `tests/regression/test_p0_hardening.py:55-90` cancel/amend, `tests/adversarial/test_untrusted.py` injection inert, `tests/adversarial/test_sections_27_30_threats.py:test_adv3035`

### Image Evidence Handling (evidence/image_interpreter.py)

* **WHAT:** `resolve_images_for_event(event_id, image_rows, media_dir)` maps `financial_events.event_id -> images.csv:related_event_id -> media/images/<image_id>.png` (file_exists check). `amount_unknown_evidence` marks blank as UNKNOWN (confidence 0, normalized `unknown`) never 0
* **WHERE:** `evidence/image_interpreter.py:resolve_images_for_event`, `amount_unknown_evidence`, `pipeline.py:_collect_evidence` (628-670) selective `needs_llm_for_image` (only blank amount + linked file)
* **WHY:** Blank `amount` MUST NOT become 0 (16 blanks ↔16 images 1:1:1 verified in `data_inventory.md`)
* **INPUTS:** `event_id`, `image_rows`, `media_dir`
* **OUTPUTS:** `list[{image_id,request_id,user_id,path,file_exists}]` + `Evidence(kind=amount)` or UNKNOWN marker
* **AUTHORITY:** Deterministic file check; vision adapter when enabled only proposes `kind==amount` (pipeline drops other kinds)
* **FAILURE MODES:** Missing file -> UNKNOWN, unreadable -> fallback, pipeline never fabricates amount
* **TEST COVERAGE:** `tests/regression/test_sections_27_30_regression.py:test_s29_image_extraction_blank_never_zero`, `tests/contract/test_phase45_contract.py:319-327` 16 bijection, `evaluation/ablation` E2 ev 11->0

### Conflict Resolution (evidence/conflict_resolver.py)

* **WHAT:** Fixed 4-rule precedence: (1) explicit cancel/settle/amend (2) newer same-source sent_at descending (3) settled over estimate (4) safer (deterministic > LLM) + source_id lexical; 3-pass stable sort `resolve`
* **WHERE:** `evidence/conflict_resolver.py:resolve` (60-83), `cancelled_event_ids`, `amended_amounts`, `amended_dates`, `detect_conflicts`
* **WHY:** Contradictory messages must have deterministic winner; LLM never reorders
* **INPUTS:** `list[Evidence]`
* **OUTPUTS:** authoritative `cancelled_set`, `amended_amounts dict`, `amended_dates dict`, `Conflict` list
* **AUTHORITY:** Deterministic code; `_method_rank` puts LLM last
* **FAILURE MODES:** Same-event cancel vs amend -> cancel wins (explicit rank 0 vs 2)
* **TEST COVERAGE:** `tests/regression/test_p0_hardening.py:12-80` 8 cases, `tests/adversarial/test_sections_27_30_threats.py:test_adv3031/3032` newer-wins + cancel>amend, `tests/regression/test_sections_27_30_regression.py:test_s29_cancellation/amendment`

### Payment Plan Generation (finance/payment_plans.py, finance/spending_changes.py)

* **WHAT:** `payment_plans.generate(state, options, safe, earliest, allows_partial)` enumerates `full` (request_date:requested), `partial` (request_date:safe | earliest:remainder) iff 5-conds (allows_partial, user accepts partial, 0<safe<requested, earliest<=deadline, exactly 2 legs sum==requested), `installments` (expand_schedule exact match, skip malformed with note), `wait` (earliest:requested iff future-safe)
* **WHERE:** `finance/payment_plans.py:generate` (20-120), `expand_schedule`, `finance/spending_changes.py:candidate_targets` (flexible-only, protected kept, ≤3, stop/reduce exclusive) `find_variants` (must flip unsafe safe)
* **WHY:** Plans must be safe across 90d and respect Tier-1 shapes; spending changes only flexible recurring in willing categories
* **INPUTS:** `FinancialState`, `payment_options`, `safe`, `earliest`, `allows_partial`, `profile`
* **OUTPUTS:** `list[Candidate(kind, payments, total_paid, option_id, changes)]` + notes
* **AUTHORITY:** Deterministic; LLM never invents schedule
* **FAILURE MODES:** Malformed option (missing freq) -> skipped + note; partial gate fails -> no partial; spending change not flipping safe -> omitted
* **TEST COVERAGE:** `tests/regression/test_sections_15_21.py` partial/installment/wait/spending, `tests/regression/test_sections_27_30_regression.py` 5 plan groups, `tests/adversarial/test_sections_27_30_threats.py` 30.5

### Payment-Plan Simulation (finance/forecast.py:simulate)

* **WHAT:** Re-simulates `state` with candidate `payments` + `changes` remapping; rejects if any day `closing<minimum` or completion `>deadline`
* **WHERE:** `finance/forecast.py:simulate` (used in `pipeline.py` validated = [c for c in eligible if simulate(...).ok] + `tests`)
* **WHY:** Safety proof before ranking; same function used in production and tests
* **INPUTS:** `FinancialState`, `payments`, `changes dict`
* **OUTPUTS:** `SimulationResult(ok, reason)`
* **AUTHORITY:** Deterministic ledger
* **FAILURE MODES:** Returns `ok=False` with reason; candidate dropped
* **TEST COVERAGE:** `tests/regression/test_sections_15_21.py:test_safe_*`, `tests/adversarial/test_sections_27_30_threats.py` boundary re-simulation

### Optimizer/Ranking (finance/optimizer.py)

* **WHAT:** `optimizer.rank_key(candidate, deadline)` 6-tuple: (1) completes by deadline (2) no spending changes (3) min total_paid (4) earlier start (5) fewer payments (6) lowest option_id; `None` option_id sorts last (`~~~`)
* **WHERE:** `finance/optimizer.py:rank_key`, `select`
* **WHY:** Official ranking is deterministic and reproducible
* **INPUTS:** `list[Candidate]`, `deadline`
* **OUTPUTS:** winner `Candidate` or `None`
* **AUTHORITY:** Deterministic tuple; LLM never ranks
* **FAILURE MODES:** Tie -> lowest option_id; reversed input same winner (stable)
* **TEST COVERAGE:** `tests/regression/test_sections_15_21.py:test_optimizer_earlier_start...`, `tests/regression/test_sections_27_30_regression.py:test_s29_deadline_boundary`, `tests/adversarial/test_sections_27_30_threats.py:test_adv3041/3046`

### Explanation Generation (output/explanation.py)

* **WHAT:** `explanation.build(decision, requested, request_date, home)` from validated `Decision` facts only (WHY+CONSTRAINT+PLAN+TIMING+EVIDENCE); `validate(text,decision)` checks no invented amounts/dates/evidence/contradiction; `build_fallback` deterministic
* **WHERE:** `output/explanation.py:build`, `build_facts`, `validate`, `build_fallback`, `pipeline.py:decide_context` 785-815
* **WHY:** Explanations must be grounded, not hallucinating
* **INPUTS:** `Decision` (8 fields + evidence)
* **OUTPUTS:** `decision_explanation: str`
* **AUTHORITY:** Validated facts only; never recomputes finance
* **FAILURE MODES:** Validation fails -> fallback template; secrets never included
* **TEST COVERAGE:** `tests/regression/test_sections_22_26.py:24.x` (6 tests: facts mismatch, invented amounts/dates, contradiction), `src/affordai/evaluation/ablation.py:instrument_e5_explanations` 250/250 valid

### Evidence Registry (evidence/evidence_registry.py)

* **WHAT:** `EvidenceRegistry(valid_event_ids, valid_message_ids, valid_image_ids)` stores `Evidence` with provenance (source_type/source_id/request_id/user_id/event_id/message_id/image_id/raw_value/normalized_value/confidence/method/extraction_method/sent_at); `add` checks source_type/kind/method allowlists, request/user ownership, event/message/image id existence, confidence [0,1], raw/normalized preservation
* **WHERE:** `evidence/evidence_registry.py:Evidence`, `EvidenceRegistry.add` (88-165), `facts_for`, `provenance`
* **WHY:** Provenance prevents fabrication and cross-request contamination
* **INPUTS:** `Evidence` + `request_id/user_id` context
* **OUTPUTS:** stored facts or `EvidenceError` rejection (recorded in `_rejected`)
* **AUTHORITY:** Deterministic validation; unknown ids/ownership rejected
* **FAILURE MODES:** Missing source_type -> rejected; wrong request/user -> `EvidenceError`; out-of-range confidence -> rejected; cross-request leaked -> rejected (tested)
* **TEST COVERAGE:** `tests/regression/test_sections_27_30_regression.py:test_s29_evidence_mismatch_rejected`, `tests/adversarial/test_untrusted.py` cross-request, `tests/contract/test_s68_integrity.py`

### Output Validator (output/validator.py, scripts/validate_output.py)

* **WHAT:** `validate_files` (structural 8 cols order, row count 250, header, PK unique, ordered), `validate_plans` (Decimal-strict, totals incl fees, installment exactness, partial 2-leg, deadline, spending ≤3 flexible-only, protected kept, event exists), `validate_evidence` (ids exist+ownership), `validate_consistency` (status<->method<->plan<->earliest<->changes<->explanation), `validate_safety` (re-simulation floor)
* **WHERE:** `output/validator.py:validate_files`, `validate_plans`, `validate_evidence`, `validate_consistency`, `validate_all` + `scripts/validate_output.py` gate (exit 1 blocks submission)
* **WHY:** Final gate: ANY hard error blocks submission (Section 26.9, checklist 22.2)
* **INPUTS:** `requests.csv`, `output.csv`, `options`, `profiles`, `decisions`, `contexts`
* **OUTPUTS:** `list[ValidationError]` with codes `OUTPUT-STRUCT/ID/NUM/ENUM/CONSISTENCY/PLAN/SPEND/EVIDENCE`
* **AUTHORITY:** Deterministic re-derivation; negative controls prove catch (reordered/invented/out-of-bounds/bogus)
* **FAILURE MODES:** Any violation -> exit 1; validator catch is SUCCESS
* **TEST COVERAGE:** `tests/regression/test_sections_22_26.py:26.x` (11 tests: structural, identity, numeric, enum, plan, spending, evidence, consistency), `tests/regression/test_sections_27_30_regression.py` row-order, `ablation.py:instrument_e6_validator` 4 controls all True

### Evaluation Harness (evaluation/*, scripts/eval_report.py)

* **WHAT:** Official-vs-local distinction (`evaluation/README.md` OFFICIAL UNKNOWN), 9 metrics `METRIC_DEFS` (structural..cost) with definition/numerator/denominator/pass_fail/official_or_local/truth_source, 5 sets manifests, baseline/final reports with deltas
* **WHERE:** `evaluation/README.md`, `src/affordai/evaluation/metrics.py` `METRIC_DEFS`+`full_dataset_metrics`+`categorize_errors`, `src/affordai/evaluation/harness.py:run_dataset`, `scripts/eval_report.py`
* **WHY:** LOCAL MEASUREMENT vs OFFICIAL UNKNOWN; sample 25 are illustrative format examples NOT eval labels
* **INPUTS:** `dataset/official` + `sample_requests.csv`
* **OUTPUTS:** `evaluation/reports/eval_baseline.json/.md`, `eval_final.json/.md` (250 rows all green, 12 failure categories all 0, deltas 0)
* **AUTHORITY:** Local proxy; never claims official score
* **FAILURE MODES:** Deltas honest (regressions reported, not hidden)
* **TEST COVERAGE:** `scripts/eval_report.py` executed 250 rows, `evaluation/datasets/*.json` manifests

### Ablation Harness (evaluation/ablation.py, scripts/run_ablation.py)

* **WHAT:** E0 deterministic baseline (mask messages/images), E1 +messages, E2 +images (UNKNOWN-safe), E3 conflict handling (instrumented 132/250 facts), E4 optimizer (6 multi-cand), E5 explanation (250/250), E6 validation (4 controls), E7 token (0 calls) -- each with explicit VERSION_DEFS, deterministic hashes (`85940ff0`/`620bff42`), same dataset/truth
* **WHERE:** `src/affordai/evaluation/ablation.py` `VERSION_DEFS`+`run_input_version`+`sample_decisions_for_version`+`instrument_*`, `scripts/run_ablation.py` tables `Version | Decision Accuracy | Plan Accuracy | Evidence | Invalid Outputs | Tokens | Cost | Runtime` + `Component | Benefit | Cost | New Failures | Decision`
* **WHY:** Determine which components measurably improve outcomes; keep only when value justifies complexity
* **INPUTS:** `dataset/official` + sample 25
* **OUTPUTS:** `evaluation/reports/ablation_results.json/.md` (E0 0.40/0.40 11ev, E1 0.44/0.48 11ev, E2 0.44/0.48 0ev, production_hash `620bff42`)
* **AUTHORITY:** Deterministic (LLM_ENABLED !=1); E3-E7 instrumented because conflict/ranking must stay authoritative (co-integration justified, not hidden fork)
* **FAILURE MODES:** E0/E1 ev 11 expected (masked images -> missing-image), E2 ev 0 after linkage
* **TEST COVERAGE:** `scripts/run_ablation.py` 23.7s, decisions KEEP with deltas documented

### Regression Suite (tests/regression/*)

* **WHAT:** Permanent capture `FAILURE->expected->actual->root->rule->fix->test->nearby->full-suite` in `tests/regression/REGRESSIONS.md` S29-R01..R05 (+ R1-R6), 15 required groups each one production-path test
* **WHERE:** `tests/regression/test_sections_27_30_regression.py` (15 tests `test_s29_*`), `test_guards.py`, `test_p0_hardening.py`, `test_sections_15_21.py`, `test_sections_22_26.py`, `REGRESSIONS.md`
* **WHY:** Bug -> rule -> test prevents recurrence
* **INPUTS:** Synthetic distinct states (no hardcoded output.csv)
* **OUTPUTS:** 15 PASS, full suite 315 green
* **AUTHORITY:** Real production calls (`simulate`, `generate`, `filter_candidates`, `RateTable`, `EvidenceRegistry`, `build_flows`, `optimizer`)
* **FAILURE MODES:** Each test fails if old bug reintroduced (e.g. partial without 0<safe<requested, RateLookup .rate vs Decimal, message_id field check)
* **TEST COVERAGE:** `pytest tests/regression/test_sections_27_30_regression.py -q` 15/15

### Adversarial Suite (tests/adversarial/*)

* **WHAT:** 29 threats 5 categories (financial 7, temporal 5, data 5, evidence 6, payment 6) with exact boundaries (floor +-0.01, deadline on/day-after, 90-day 89/90, Feb 28/29, injection 4 variants)
* **WHERE:** `tests/adversarial/test_sections_27_30_threats.py` `test_adv3001..3046`, `docs/threat-model.md` 30.1-30.5, `tests/adversarial/test_untrusted.py`
* **WHY:** Messages/images are UNTRUSTED EVIDENCE that never override contract/ranking/safety
* **INPUTS:** Synthetic `FinancialState`/`Evidence`/`Candidate`
* **OUTPUTS:** 29 PASS, injection -> non-positive/unlinked only, floor unmoved
* **AUTHORITY:** Deterministic floor `simulate`, `conflict_resolver` 4-rule, pipeline `kind!=amount` drop
* **FAILURE MODES:** No crash, no fabricated amount, no cross-request, safe fallback
* **TEST COVERAGE:** `pytest tests/adversarial/test_sections_27_30_threats.py -q` 29/29

### Token Accounting (evaluation/usage.py, llm_adapter.py, pipeline.py)

* **WHAT:** Every model call captures `ModelCallRecord` (provider/model/purpose/input/output tokens/success/retry/fallback) via `llm_adapter.ModelCallRecord`; `UsageReport` aggregates calls/in/out/total/avg/cost per-request + per-model breakdown; `PRICING` dict separate (empty -> cost 0 for 0 calls, UNKNOWN when calls>0 but pricing unverified)
* **WHERE:** `src/affordai/evaluation/usage.py:UsageReport` `PRICING`, `to_markdown`, `src/affordai/evidence/llm_adapter.py:ModelCallRecord` `needs_llm_for_messages/image` `check_batch_safe` `minimize_message_context`, `src/affordai/pipeline.py:_collect_evidence` selective calls + `run` per_model aggregation, `scripts/build_output.py` persists FINAL run to `evaluation/usage_report.md`
* **WHY:** Deterministic E0 runs with 0 calls/0 tokens/0 cost; when enabled, selective triggers + minimized contexts + batch safety keep cost minimal without correctness loss
* **INPUTS:** `ctx.messages`/`images` + `LlmConfig` (env `LLM_ENABLED !=1` -> disabled)
* **OUTPUTS:** `evaluation/usage_report.md` (0 calls/0 tokens 2.6s, no prompts/secrets)
* **AUTHORITY:** `check_batch_safe` enforces one request/user per call; `redact` before storage; financial decisions never depend on tokens
* **FAILURE MODES:** No division-by-zero (avg handles 0), no fake 0 cost when pricing unknown (returns UNKNOWN), deterministic 0-call valid
* **TEST COVERAGE:** `evaluation/ablation.py:instrument_e7_tokens` 0 calls, `tests/security/test_sec31_32.py` batch safety, `pipeline` records 0 in E0

### Clean-Room Execution (scripts/clean_room_run.py)

* **WHAT:** Fresh subprocess scrubbed env (`no KEY/TOKEN` in env), temp dir `affordai-cleanroom-*`, `build_output.py --dataset dataset/official --out <tmp>/output.csv` -> `validate_output.py` gate, no hidden local state, no dependency install needed
* **WHERE:** `scripts/clean_room_run.py:main` (subprocess `sys.executable scripts/build_output.py` + `validate_output.py` with timeout 1200/600)
* **WHY:** Proves reproducibility from scratch (evaluator simulation)
* **INPUTS:** `dataset/official` on disk
* **OUTPUTS:** `CLEAN-ROOM PASS` (250 rows, validator PASS, 3.0s)
* **AUTHORITY:** Stdlib only (pandas listed but unused at runtime)
* **FAILURE MODES:** Non-zero build/validate -> `CLEAN-ROOM FAIL`
* **TEST COVERAGE:** Executed 2026-09-13 16:34 and 16:51 IST both PASS, replay hash identical

## Q&A: Authority & Fallback

* **Deterministic core authority:** balances, income/expenses, minimum, amounts/dates, forecast, 90-day sim, decision rules, deadline, plan validity/ranking, final validation -- all deterministic (`finance/*`, `decision/*`, `output/validator`). LLM `!= financial authority` (proved via `tests/regression/test_sections_15_21.py:test_no_llm_or_clock_in_deterministic_core` grep for `propose_facts`/`openai`/`date.today` absence).
* **Fallback:** Per-request `pipeline._decide_safe` degrades to `not_affordable/none/0` preserving `safe/earliest` when derivable, never crashes batch (`tests/regression/test_guards.py:test_r6_per_request_fallback_never_crashes_batch`).

## Worked Examples

* **Normal (request allows full):** opening 20000/minimum 3000/requested 4000 -> `max_safe_today` 4000 -> `earliest` REQ -> candidates `full` safe -> `full` selected -> `affordable_now/full_payment/REQ:4000/REQ/none`
* **Ambiguous (message amend):** `Please update amount to 2500 for next month.` with `related_event_id e-am` -> `interpret` amend_amount 2500 -> `conflict_resolver.amended_amounts` -> `build_flows` re-maps -> re-simulates
* **Image-only (blank amount):** `event amount None` -> `resolve_images_for_event` finds linked PNG -> vision disabled -> `amount_unknown_evidence` UNKNOWN (never 0) -> plan must stay safe without it; E2 linkage clears 11 ev errors
* **Conflict (cancel vs amend same event):** `amend_amount 50` + `cancel e-2` -> `resolve` cancel rank 0 wins -> `cancelled_event_ids` includes e-2 -> `build_flows` drops event
* **Installment (exactness):** `opt_7` 3 payments `first 2025-01-10 freq 30 fee 200 total 3200` -> `expand_schedule` legs exact -> `Candidate` `option_id opt_7 total 3200` -> `validate_plans` re-derives totals incl fees -> ranking 6-tuple picks lowest `total` then `option_id`
