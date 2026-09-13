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
* **ALTERNATIVE DESIGN:** Agent/orchestration graph that delegates decide to an LLM planner.
* **TRADE-OFF:** Straight-line code is longer to write than prompting but is reproducible and debuggable (hash-identical replay).
* **REAL EXAMPLE:** `request_26` → decide_context returns Decision safe 15656000 in one pass.
* **LIMITATION:** Synchronous single-threaded; no parallel sharding for very large portfolios (not needed for 250 rows).

### Forecast & Balance Simulation (finance/forecast.py, finance/state.py, finance/timeline.py)

* **WHAT:** Daily ledger 90 days inclusive (`temporal.forecast_end = request_date+89`), `simulate(state,payments,changes).ok` checks `closing_balance >= minimum` every day + deadline
* **WHERE:** `finance/forecast.py:simulate` (40-120), `max_safe_today` (binary search ROUND_FLOOR), `earliest_full_date` (forward scan), `finance/state.py:build` (opening/minimum/requested, daily_net), `finance/timeline.py:build_flows` (scheduled/settled future + message-confirmed salary)
* **WHY:** Central invariant: plan safe ONLY if floor holds every projected day and completes by `desired_completion_date`. Pending credits ignored, pending debits reserved, duplicate/failed/cancelled excluded, FX via `RateTable`
* **INPUTS:** `FinancialState`, candidate `payments: list[(date,Decimal)]`
* **OUTPUTS:** `SimulationResult(ok, reason, daily_closings)`, `safe: Decimal` (0<=safe<=requested), `earliest: date|None`
* **AUTHORITY:** Deterministic Decimal arithmetic, `ROUND_FLOOR` for safe, binary search monotonicity lemma
* **FAILURE MODES:** `MissingRateError` fail-closed (no foreign credit), empty window -> safe 0, breached baseline -> early-return
* **TEST COVERAGE:** `tests/regression/test_sections_15_21.py` safe bounds/monotone, earliest minimality, `tests/adversarial/test_sections_12_14_adversarial.py` window/boundary, `tests/edge_cases/test_boundaries.py` floor exact
* **ALTERNATIVE DESIGN:** Closed-form balance equation solving for safe amount.
* **TRADE-OFF:** Daily loop is ~8ms per request (measured) but handles month-end clamping and conditional flows exactly.
* **REAL EXAMPLE:** `request_36` forward scan finds 2026-08-15 first safe single-payment day.
* **LIMITATION:** 31 days per month approximation for installment term and recurrence thresholds remain UNPROVEN (spec §7).

### Decision Rules (decision/rules.py, decision/decision.py, decision/invariants.py)

* **WHAT:** `rules.derive(winner)` -> `(status,method)` mapping: `full->affordable_now`, `partial/installments+changes->affordable_with_plan`, `wait->affordable_later`, `None->not_affordable/not_recommended`
* **WHERE:** `decision/rules.py:derive`, `decision/decision.py` `Decision` dataclass (OUTPUT_COLUMNS order, frozen, __post_init__ checks 0<=safe<=requested + status/method/earliest consistency), `decision/invariants.py` `check_earliest_consistency`
* **WHY:** Status<->method<->plan<->earliest must be consistent per Tier-1 contract (decision-matrix A-E)
* **INPUTS:** `Candidate|None`
* **OUTPUTS:** `(affordability_status, recommended_payment_method)` enums strict
* **AUTHORITY:** Deterministic code; LLM never decides
* **FAILURE MODES:** Invariant violation -> `_fallback_decision` + `trace` record
* **TEST COVERAGE:** `tests/regression/test_sections_15_21.py:test_rules_derive_full_mapping`, `tests/regression/test_sections_22_26.py` invariants, `tests/unit/test_contract_invariants.py`
* **ALTERNATIVE DESIGN:** LLM classifies status/method from explanation text.
* **TRADE-OFF:** Hard-coded mapping is rigid but Tier-1 contract makes rigidity required.
* **REAL EXAMPLE:** `request_30` winner `installments` → derive gives `affordable_with_plan / installments`.
* **LIMITATION:** Mapping cannot express new statuses without code change; no dynamic taxonomy.

### Message Interpretation (evidence/message_interpreter.py, evidence/llm_adapter.py, evidence/message_income.py)

* **WHAT:** Deterministic regex `interpret(message)` emits typed facts only (`cancel/settle/confirm/delay/amend_amount/amend_date/preference`), never financial decisions. Salary confirmation via `message_income.confirmed_series` (employer+confirm semantics+salary keywords, deny-first)
* **WHERE:** `evidence/message_interpreter.py:interpret` (47-98), `_PATTERNS`/`_AMOUNT_RE`/`SALARY_RE`, `evidence/message_income.py:confirmed_series`, `evidence/llm_adapter.py:propose_facts` (bounded, schema-validated, 0 in E0)
* **WHY:** Messages are UNTRUSTED EVIDENCE; rule engine never reads raw text so `ignore minimum` cannot override floor
* **INPUTS:** single `message` dict (message_id/user_id/request_id/related_event_id/message_text/sent_at)
* **OUTPUTS:** `list[Evidence]` with provenance (source_type/message_id/request_id/user_id/event_id/raw/normalized/confidence=1.0/method=deterministic)
* **AUTHORITY:** Deterministic regex; LLM adapter only proposes typed facts (validated-or-dropped, confidence >=0.80, `needs_llm_for_messages` selective)
* **FAILURE MODES:** No pattern -> 0 facts (safe), payroll ref `EMP-0001` never parses as amount, injection `0` parsed but dropped by `parse_amount>0` + event_id gate + floor re-simulation
* **TEST COVERAGE:** `tests/regression/test_p0_hardening.py:55-90` cancel/amend, `tests/adversarial/test_untrusted.py` injection inert, `tests/adversarial/test_sections_27_30_threats.py:test_adv3035`
* **ALTERNATIVE DESIGN:** LLM-first extraction over all 215 messages.
* **TRADE-OFF:** Regex is cheap/deterministic but misses novel phrasing → covered by selective LLM fallback.
* **REAL EXAMPLE:** `message_26` payroll increase → no amount fact (payroll ref not an amount), `confirmed_series` adds salary flow.
* **LIMITATION:** 20-char heuristic + salary keyword list tuned, not proven complete (INFERENCE).

### Image Evidence Handling (evidence/image_interpreter.py)

* **WHAT:** `resolve_images_for_event(event_id, image_rows, media_dir)` maps `financial_events.event_id -> images.csv:related_event_id -> media/images/<image_id>.png` (file_exists check). `amount_unknown_evidence` marks blank as UNKNOWN (confidence 0, normalized `unknown`) never 0
* **WHERE:** `evidence/image_interpreter.py:resolve_images_for_event`, `amount_unknown_evidence`, `pipeline.py:_collect_evidence` (628-670) selective `needs_llm_for_image` (only blank amount + linked file)
* **WHY:** Blank `amount` MUST NOT become 0 (16 blanks ↔16 images 1:1:1 verified in `data_inventory.md`)
* **INPUTS:** `event_id`, `image_rows`, `media_dir`
* **OUTPUTS:** `list[{image_id,request_id,user_id,path,file_exists}]` + `Evidence(kind=amount)` or UNKNOWN marker
* **AUTHORITY:** Deterministic file check; vision adapter when enabled only proposes `kind==amount` (pipeline drops other kinds)
* **FAILURE MODES:** Missing file -> UNKNOWN, unreadable -> fallback, pipeline never fabricates amount
* **TEST COVERAGE:** `tests/regression/test_sections_27_30_regression.py:test_s29_image_extraction_blank_never_zero`, `tests/contract/test_phase45_contract.py:319-327` 16 bijection, `evaluation/ablation` E2 ev 11->0
* **ALTERNATIVE DESIGN:** Run vision on all 16 PNGs blindly.
* **TRADE-OFF:** Linkage-first UNKNOWN-safe reduces recall but never fabricates a zero.
* **REAL EXAMPLE:** `request_33` blank event linked via `image_06` → UNKNOWN marker, decision `not_affordable`.
* **LIMITATION:** Without a vendored vision backend, pictured amounts never resolve (documented, metered 0 facts added).

### Conflict Resolution (evidence/conflict_resolver.py)

* **WHAT:** Fixed 4-rule precedence: (1) explicit cancel/settle/amend (2) newer same-source sent_at descending (3) settled over estimate (4) safer (deterministic > LLM) + source_id lexical; 3-pass stable sort `resolve`
* **WHERE:** `evidence/conflict_resolver.py:resolve` (60-83), `cancelled_event_ids`, `amended_amounts`, `amended_dates`, `detect_conflicts`
* **WHY:** Contradictory messages must have deterministic winner; LLM never reorders
* **INPUTS:** `list[Evidence]`
* **OUTPUTS:** authoritative `cancelled_set`, `amended_amounts dict`, `amended_dates dict`, `Conflict` list
* **AUTHORITY:** Deterministic code; `_method_rank` puts LLM last
* **FAILURE MODES:** Same-event cancel vs amend -> cancel wins (explicit rank 0 vs 2)
* **TEST COVERAGE:** `tests/regression/test_p0_hardening.py:12-80` 8 cases, `tests/adversarial/test_sections_27_30_threats.py:test_adv3031/3032` newer-wins + cancel>amend, `tests/regression/test_sections_27_30_regression.py:test_s29_cancellation/amendment`
* **ALTERNATIVE DESIGN:** Recency-only or LLM-judged precedence.
* **TRADE-OFF:** Fixed 4-rule order can mishandle genuinely ambiguous cases → falls back to safest interpretation.
* **REAL EXAMPLE:** Synthetic `cancel e-2` vs `amend_amount 50` → cancel rank 0 wins (tested 8 cases in p0_hardening).
* **LIMITATION:** 4-rule order is Tier-1-derived, not officially published as verbatim text (INFERENCE, documented).

### Payment Plan Generation (finance/payment_plans.py, finance/spending_changes.py)

* **WHAT:** `payment_plans.generate(state, options, safe, earliest, allows_partial)` enumerates `full` (request_date:requested), `partial` (request_date:safe | earliest:remainder) iff 5-conds (allows_partial, user accepts partial, 0<safe<requested, earliest<=deadline, exactly 2 legs sum==requested), `installments` (expand_schedule exact match, skip malformed with note), `wait` (earliest:requested iff future-safe)
* **WHERE:** `finance/payment_plans.py:generate` (20-120), `expand_schedule`, `finance/spending_changes.py:candidate_targets` (flexible-only, protected kept, ≤3, stop/reduce exclusive) `find_variants` (must flip unsafe safe)
* **WHY:** Plans must be safe across 90d and respect Tier-1 shapes; spending changes only flexible recurring in willing categories
* **INPUTS:** `FinancialState`, `payment_options`, `safe`, `earliest`, `allows_partial`, `profile`
* **OUTPUTS:** `list[Candidate(kind, payments, total_paid, option_id, changes)]` + notes
* **AUTHORITY:** Deterministic; LLM never invents schedule
* **FAILURE MODES:** Malformed option (missing freq) -> skipped + note; partial gate fails -> no partial; spending change not flipping safe -> omitted
* **TEST COVERAGE:** `tests/regression/test_sections_15_21.py` partial/installment/wait/spending, `tests/regression/test_sections_27_30_regression.py` 5 plan groups, `tests/adversarial/test_sections_27_30_threats.py` 30.5
* **ALTERNATIVE DESIGN:** Let LLM propose schedules.
* **TRADE-OFF:** Enumerating 4 kinds deterministically is more code but guarantees Tier-1 shape compliance.
* **REAL EXAMPLE:** `request_30` → 3-leg installments via `expand_schedule` exact match, `request_26` → single-leg full.
* **LIMITATION:** `partial_payment` has 0 production rows; engine proven only via synthetic regression tests.

### Payment-Plan Simulation (finance/forecast.py:simulate)

* **WHAT:** Re-simulates `state` with candidate `payments` + `changes` remapping; rejects if any day `closing<minimum` or completion `>deadline`
* **WHERE:** `finance/forecast.py:simulate` (used in `pipeline.py` validated = [c for c in eligible if simulate(...).ok] + `tests`)
* **WHY:** Safety proof before ranking; same function used in production and tests
* **INPUTS:** `FinancialState`, `payments`, `changes dict`
* **OUTPUTS:** `SimulationResult(ok, reason)`
* **AUTHORITY:** Deterministic ledger
* **FAILURE MODES:** Returns `ok=False` with reason; candidate dropped
* **TEST COVERAGE:** `tests/regression/test_sections_15_21.py:test_safe_*`, `tests/adversarial/test_sections_27_30_threats.py` boundary re-simulation
* **ALTERNATIVE DESIGN:** Separate ad-hoc safety check per plan type.
* **TRADE-OFF:** Single `simulate` function is reused 90+ times per request (cost) but ensures one invariant proof site.
* **REAL EXAMPLE:** `request_30` installments each leg re-simulated; floor holds on 2026-06-05 completion.
* **LIMITATION:** Re-simulation is pure ledger walk; no stochastic spending model.

### Optimizer/Ranking (finance/optimizer.py)

* **WHAT:** `optimizer.rank_key(candidate, deadline)` 6-tuple: (1) completes by deadline (2) no spending changes (3) min total_paid (4) earlier start (5) fewer payments (6) lowest option_id; `None` option_id sorts last (`~~~`)
* **WHERE:** `finance/optimizer.py:rank_key`, `select`
* **WHY:** Official ranking is deterministic and reproducible
* **INPUTS:** `list[Candidate]`, `deadline`
* **OUTPUTS:** winner `Candidate` or `None`
* **AUTHORITY:** Deterministic tuple; LLM never ranks
* **FAILURE MODES:** Tie -> lowest option_id; reversed input same winner (stable)
* **TEST COVERAGE:** `tests/regression/test_sections_15_21.py:test_optimizer_earlier_start...`, `tests/regression/test_sections_27_30_regression.py:test_s29_deadline_boundary`, `tests/adversarial/test_sections_27_30_threats.py:test_adv3041/3046`
* **ALTERNATIVE DESIGN:** Weighted scoring or LLM ranking.
* **TRADE-OFF:** Lexicographic 6-tuple can prefer slightly costlier on-time plan — intended per contract (deadline first).
* **REAL EXAMPLE:** Multi-candidate test with identical deadline and no-change flag → lowest total wins, tie → lowest option id.
* **LIMITATION:** Ranking cannot express user subjective preference beyond the 6 fixed keys.

### Explanation Generation (output/explanation.py)

* **WHAT:** `explanation.build(decision, requested, request_date, home)` from validated `Decision` facts only (WHY+CONSTRAINT+PLAN+TIMING+EVIDENCE); `validate(text,decision)` checks no invented amounts/dates/evidence/contradiction; `build_fallback` deterministic
* **WHERE:** `output/explanation.py:build`, `build_facts`, `validate`, `build_fallback`, `pipeline.py:decide_context` 785-815
* **WHY:** Explanations must be grounded, not hallucinating
* **INPUTS:** `Decision` (8 fields + evidence)
* **OUTPUTS:** `decision_explanation: str`
* **AUTHORITY:** Validated facts only; never recomputes finance
* **FAILURE MODES:** Validation fails -> fallback template; secrets never included
* **TEST COVERAGE:** `tests/regression/test_sections_22_26.py:24.x` (6 tests: facts mismatch, invented amounts/dates, contradiction), `src/affordai/evaluation/ablation.py:instrument_e5_explanations` 250/250 valid
* **ALTERNATIVE DESIGN:** Free-form LLM summary of decision.
* **TRADE-OFF:** Template over Decision facts is stilted prose but `validate` stays 250/250 (no hallucinations).
* **REAL EXAMPLE:** `request_26` explanation cites safe 15656000 and plan `2025-08-03:15656000` verbatim from Decision.
* **LIMITATION:** Templates don't localize multilingual input; no per-user toning.

### Evidence Registry (evidence/evidence_registry.py)

* **WHAT:** `EvidenceRegistry(valid_event_ids, valid_message_ids, valid_image_ids)` stores `Evidence` with provenance (source_type/source_id/request_id/user_id/event_id/message_id/image_id/raw_value/normalized_value/confidence/method/extraction_method/sent_at); `add` checks source_type/kind/method allowlists, request/user ownership, event/message/image id existence, confidence [0,1], raw/normalized preservation
* **WHERE:** `evidence/evidence_registry.py:Evidence`, `EvidenceRegistry.add` (88-165), `facts_for`, `provenance`
* **WHY:** Provenance prevents fabrication and cross-request contamination
* **INPUTS:** `Evidence` + `request_id/user_id` context
* **OUTPUTS:** stored facts or `EvidenceError` rejection (recorded in `_rejected`)
* **AUTHORITY:** Deterministic validation; unknown ids/ownership rejected
* **FAILURE MODES:** Missing source_type -> rejected; wrong request/user -> `EvidenceError`; out-of-range confidence -> rejected; cross-request leaked -> rejected (tested)
* **TEST COVERAGE:** `tests/regression/test_sections_27_30_regression.py:test_s29_evidence_mismatch_rejected`, `tests/adversarial/test_untrusted.py` cross-request, `tests/contract/test_s68_integrity.py`
* **ALTERNATIVE DESIGN:** Trust all extracted facts without registry checks.
* **TRADE-OFF:** Ownership + allowlist checks add per-fact cost but prevent cross-request contamination (tested).
* **REAL EXAMPLE:** Cross-request fact for `request_03` injected into `request_30` → `EvidenceError` rejected (test_untrusted).
* **LIMITATION:** Registry is in-memory per request; no persistent provenance store beyond RequestTrace.

### Output Validator (output/validator.py, scripts/validate_output.py)

* **WHAT:** `validate_files` (structural 8 cols order, row count 250, header, PK unique, ordered), `validate_plans` (Decimal-strict, totals incl fees, installment exactness, partial 2-leg, deadline, spending ≤3 flexible-only, protected kept, event exists), `validate_evidence` (ids exist+ownership), `validate_consistency` (status<->method<->plan<->earliest<->changes<->explanation), `validate_safety` (re-simulation floor)
* **WHERE:** `output/validator.py:validate_files`, `validate_plans`, `validate_evidence`, `validate_consistency`, `validate_all` + `scripts/validate_output.py` gate (exit 1 blocks submission)
* **WHY:** Final gate: ANY hard error blocks submission (Section 26.9, checklist 22.2)
* **INPUTS:** `requests.csv`, `output.csv`, `options`, `profiles`, `decisions`, `contexts`
* **OUTPUTS:** `list[ValidationError]` with codes `OUTPUT-STRUCT/ID/NUM/ENUM/CONSISTENCY/PLAN/SPEND/EVIDENCE`
* **AUTHORITY:** Deterministic re-derivation; negative controls prove catch (reordered/invented/out-of-bounds/bogus)
* **FAILURE MODES:** Any violation -> exit 1; validator catch is SUCCESS
* **TEST COVERAGE:** `tests/regression/test_sections_22_26.py:26.x` (11 tests: structural, identity, numeric, enum, plan, spending, evidence, consistency), `tests/regression/test_sections_27_30_regression.py` row-order, `ablation.py:instrument_e6_validator` 4 controls all True
* **ALTERNATIVE DESIGN:** Best-effort warnings instead of exit-1 gate.
* **TRADE-OFF:** Hard gate blocks submission on any error but mutation tests prove it catches 13/13 forgeries.
* **REAL EXAMPLE:** Reordered `output.csv` (reverse input order) → `OUTPUT-STRUCT` error; invented plan totals → `PLAN` error.
* **LIMITATION:** Evidence/spending validators are post-hoc; they cannot retroactively create a safe plan, only block bad rows.

### Evaluation Harness (evaluation/*, scripts/eval_report.py)

* **WHAT:** Official-vs-local distinction (`evaluation/README.md` OFFICIAL UNKNOWN), 9 metrics `METRIC_DEFS` (structural..cost) with definition/numerator/denominator/pass_fail/official_or_local/truth_source, 5 sets manifests, baseline/final reports with deltas
* **WHERE:** `evaluation/README.md`, `src/affordai/evaluation/metrics.py` `METRIC_DEFS`+`full_dataset_metrics`+`categorize_errors`, `src/affordai/evaluation/harness.py:run_dataset`, `scripts/eval_report.py`
* **WHY:** LOCAL MEASUREMENT vs OFFICIAL UNKNOWN; sample 25 are illustrative format examples NOT eval labels
* **INPUTS:** `dataset/official` + `sample_requests.csv`
* **OUTPUTS:** `evaluation/reports/eval_baseline.json/.md`, `eval_final.json/.md` (250 rows all green, 12 failure categories all 0, deltas 0)
* **AUTHORITY:** Local proxy; never claims official score
* **FAILURE MODES:** Deltas honest (regressions reported, not hidden)
* **TEST COVERAGE:** `scripts/eval_report.py` executed 250 rows, `evaluation/datasets/*.json` manifests
* **ALTERNATIVE DESIGN:** Claim local accuracy equals official score.
* **TRADE-OFF:** Local proxy is honest UNKNOWN vs official but gives actionable structural/numerical gates.
* **REAL EXAMPLE:** 250-row full run → 0 structural, 0 plan, 0 evidence errors, replay `d8386548` identical.
* **LIMITATION:** Hidden official judging may weight samples differently; local proxy cannot reproduce it.

### Ablation Harness (evaluation/ablation.py, scripts/run_ablation.py)

* **WHAT:** E0 deterministic baseline (mask messages/images), E1 +messages, E2 +images (UNKNOWN-safe), E3 conflict handling (instrumented 132/250 facts), E4 optimizer (6 multi-cand), E5 explanation (250/250), E6 validation (4 controls), E7 token (0 calls) -- each with explicit VERSION_DEFS, deterministic hashes (`85940ff0`/`620bff42`), same dataset/truth
* **WHERE:** `src/affordai/evaluation/ablation.py` `VERSION_DEFS`+`run_input_version`+`sample_decisions_for_version`+`instrument_*`, `scripts/run_ablation.py` tables `Version | Decision Accuracy | Plan Accuracy | Evidence | Invalid Outputs | Tokens | Cost | Runtime` + `Component | Benefit | Cost | New Failures | Decision`
* **WHY:** Determine which components measurably improve outcomes; keep only when value justifies complexity
* **INPUTS:** `dataset/official` + sample 25
* **OUTPUTS:** `evaluation/reports/ablation_results.json/.md` (E0 0.40/0.40 11ev, E1 0.44/0.48 11ev, E2 0.44/0.48 0ev, production_hash `620bff42`)
* **AUTHORITY:** Deterministic (LLM_ENABLED !=1); E3-E7 instrumented because conflict/ranking must stay authoritative (co-integration justified, not hidden fork)
* **FAILURE MODES:** E0/E1 ev 11 expected (masked images -> missing-image), E2 ev 0 after linkage
* **TEST COVERAGE:** `scripts/run_ablation.py` 23.7s, decisions KEEP with deltas documented
* **ALTERNATIVE DESIGN:** Report only accuracy numbers.
* **TRADE-OFF:** Instrumented E3–E7 add harness code but prove each component's keep/remove decision with tables.
* **REAL EXAMPLE:** E2 linkage clears 11 evidence errors (11 → 0) while E0/E1 keep them masked.
* **LIMITATION:** E3–E7 are instrumented, not separate runnable modes (co-integration justified, not a hidden fork).

### Regression Suite (tests/regression/*)

* **WHAT:** Permanent capture `FAILURE->expected->actual->root->rule->fix->test->nearby->full-suite` in `tests/regression/REGRESSIONS.md` S29-R01..R05 (+ R1-R6), 15 required groups each one production-path test
* **WHERE:** `tests/regression/test_sections_27_30_regression.py` (15 tests `test_s29_*`), `test_guards.py`, `test_p0_hardening.py`, `test_sections_15_21.py`, `test_sections_22_26.py`, `REGRESSIONS.md`
* **WHY:** Bug -> rule -> test prevents recurrence
* **INPUTS:** Synthetic distinct states (no hardcoded output.csv)
* **OUTPUTS:** 15 PASS, full suite 315 green
* **AUTHORITY:** Real production calls (`simulate`, `generate`, `filter_candidates`, `RateTable`, `EvidenceRegistry`, `build_flows`, `optimizer`)
* **FAILURE MODES:** Each test fails if old bug reintroduced (e.g. partial without 0<safe<requested, RateLookup .rate vs Decimal, message_id field check)
* **TEST COVERAGE:** `pytest tests/regression/test_sections_27_30_regression.py -q` 15/15
* **ALTERNATIVE DESIGN:** Ad-hoc bug fixes without regression capture.
* **TRADE-OFF:** 15-group suite + 29 adversarial tests increase CI time (~93s) but prevent recurrence.
* **REAL EXAMPLE:** `test_s29_image_extraction_blank_never_zero` guards blank ≠ 0 invariant forever.
* **LIMITATION:** Synthetic edge cases may not cover every real-world message phrasing.

### Adversarial Suite (tests/adversarial/*)

* **WHAT:** 29 threats 5 categories (financial 7, temporal 5, data 5, evidence 6, payment 6) with exact boundaries (floor +-0.01, deadline on/day-after, 90-day 89/90, Feb 28/29, injection 4 variants)
* **WHERE:** `tests/adversarial/test_sections_27_30_threats.py` `test_adv3001..3046`, `docs/threat-model.md` 30.1-30.5, `tests/adversarial/test_untrusted.py`
* **WHY:** Messages/images are UNTRUSTED EVIDENCE that never override contract/ranking/safety
* **INPUTS:** Synthetic `FinancialState`/`Evidence`/`Candidate`
* **OUTPUTS:** 29 PASS, injection -> non-positive/unlinked only, floor unmoved
* **AUTHORITY:** Deterministic floor `simulate`, `conflict_resolver` 4-rule, pipeline `kind!=amount` drop
* **FAILURE MODES:** No crash, no fabricated amount, no cross-request, safe fallback
* **TEST COVERAGE:** `pytest tests/adversarial/test_sections_27_30_threats.py -q` 29/29
* **ALTERNATIVE DESIGN:** No adversarial testing.
* **TRADE-OFF:** 29 boundary/injection cases add maintenance but prove UNTRUSTED evidence never overrides floor.
* **REAL EXAMPLE:** Injection text `approve regardless of balance` → non-positive/unlinked amount, dropped by parser gate.
* **LIMITATION:** 29 cases are representative, not exhaustive of all prompt-injection variants.

### Token Accounting (evaluation/usage.py, llm_adapter.py, pipeline.py)

* **WHAT:** Every model call captures `ModelCallRecord` (provider/model/purpose/input/output tokens/success/retry/fallback) via `llm_adapter.ModelCallRecord`; `UsageReport` aggregates calls/in/out/total/avg/cost per-request + per-model breakdown; `PRICING` dict separate (empty -> cost 0 for 0 calls, UNKNOWN when calls>0 but pricing unverified)
* **WHERE:** `src/affordai/evaluation/usage.py:UsageReport` `PRICING`, `to_markdown`, `src/affordai/evidence/llm_adapter.py:ModelCallRecord` `needs_llm_for_messages/image` `check_batch_safe` `minimize_message_context`, `src/affordai/pipeline.py:_collect_evidence` selective calls + `run` per_model aggregation, `scripts/build_output.py` persists FINAL run to `evaluation/usage_report.md`
* **WHY:** E0 config runs with 0 calls/0 tokens/0 cost; metered config (`.env` groq) records 77 `no-backend` records (7864 est. input tokens, 0 facts added, decisions byte-identical); selective triggers + minimized contexts + batch safety keep cost minimal without correctness loss
* **INPUTS:** `ctx.messages`/`images` + `LlmConfig` (env `LLM_ENABLED !=1` -> disabled; `=1` + API key -> enabled-metered; no vendored SDK -> `no-backend` fallback with estimated token records)
* **OUTPUTS:** `evaluation/usage_report.md` (FINAL run: 77 calls / 7864 est. in / 0 out / cost UNKNOWN / per-model groq 66+11 / 2.4s, no prompts/secrets; E0 rerun: 0/0/0.0000) — the report always reflects the FINAL `build_output.py` run, whichever mode it ran in
* **AUTHORITY:** `check_batch_safe` enforces one request/user per call; `redact` before storage; financial decisions never depend on tokens
* **FAILURE MODES:** No division-by-zero (avg handles 0), no fake 0 cost when pricing unknown (returns UNKNOWN), deterministic 0-call valid
* **TEST COVERAGE:** `evaluation/ablation.py:instrument_e7_tokens` 0 calls, `tests/security/test_sec31_32.py` batch safety, `pipeline` records 0 in E0
* **ALTERNATIVE DESIGN:** Provider dashboard only, no local accounting.
* **TRADE-OFF:** Local chars/4 estimates are coarse → labelled `estimated`; provider values win when present, but per-request attribution is local.
* **REAL EXAMPLE:** Metered FINAL run 77 attempt-records (66 message + 11 image), 7864 est. input tokens, 0 facts added, hash unchanged.
* **LIMITATION:** Cost is UNKNOWN without verified `PRICING` entries; never fabricated as 0 beyond E0.

### Clean-Room Execution (scripts/clean_room_run.py)

* **WHAT:** Fresh subprocess scrubbed env (`no KEY/TOKEN` in env), temp dir `affordai-cleanroom-*`, `build_output.py --dataset dataset/official --out <tmp>/output.csv` -> `validate_output.py` gate, no hidden local state, no dependency install needed
* **WHERE:** `scripts/clean_room_run.py:main` (subprocess `sys.executable scripts/build_output.py` + `validate_output.py` with timeout 1200/600)
* **WHY:** Proves reproducibility from scratch (evaluator simulation)
* **INPUTS:** `dataset/official` on disk
* **OUTPUTS:** `CLEAN-ROOM PASS` (250 rows, validator PASS, 3.0s)
* **AUTHORITY:** Stdlib only (pandas listed but unused at runtime)
* **FAILURE MODES:** Non-zero build/validate -> `CLEAN-ROOM FAIL`
* **TEST COVERAGE:** Executed 2026-09-13 16:34 and 16:51 IST both PASS, replay hash identical
* **ALTERNATIVE DESIGN:** Trust local dev environment without clean-room.
* **TRADE-OFF:** Subprocess clean-room adds ~3s but proves no hidden local-state dependency (evaluator simulation).
* **REAL EXAMPLE:** `scripts/clean_room_run.py` fresh subprocess → 250 rows validator PASS 2026-09-13.
* **LIMITATION:** Checked-in venv or network-dependent model backends are not simulated in the clean subprocess.

### Ingestion and Request Context (ingestion/*, pipeline.py:RequestContext, build_contexts)

* **WHAT:** Typed CSV loaders per table, PK deduplication (`_dedupe_by_key`), FK validation (`_validate_fk_integrity`, `_validate_request_identity`), indexed joins `by_user/by_request`, `RequestContext(original_index, request_id, user_id, request, profile, events, messages, images, payment_options, evidence)` preserving row identity end-to-end.
* **WHERE:** `src/affordai/ingestion/*.py` loaders, `src/affordai/pipeline.py:41-95` `RequestContext`, `191-230 _dedupe`, `233-390 build_contexts`, `393-557 FK checks`, `_resolve_dataset_path` dual-layout `dataset/` vs `dataset/official`.
* **WHY:** Row identity loss (prior Orchestrate failure) and orphan joins would corrupt the 250-row output order.
* **INPUTS:** Raw CSV rows + `dataset_dir` path
* **OUTPUTS:** `tables` dict + `list[RequestContext]` sorted deterministically (events by settlement_date, messages by sent_at)
* **AUTHORITY:** Deterministic join; no LLM ever touches IDs or ordering.
* **FAILURE MODES:** Duplicate PK → `DatasetError`; orphan FK → `JoinIntegrityIssue` recorded, per-request fallback still produces a safe row.
* **TEST COVERAGE:** `tests/contract/test_phase45_contract.py` PK uniqueness + 16↔16 bijections; `tests/contract/test_s68_integrity.py` row identity + orphan 0.
* **ALTERNATIVE DESIGN:** Naive pandas merges in one line per table.
* **TRADE-OFF:** Explicit dedupe + join audit is more code but makes row mismatch impossible (validator still re-checks).
* **REAL EXAMPLE:** `request_26` → `by_user` lookup finds profile+events+options for `user_26` with `original_index` 0 → output row 0 stays `request_26`.
* **LIMITATION:** Dual-layout resolver only covers `dataset/` and `dataset/official` prefixes, not arbitrary nested layouts.

### Eligibility Gate (decision/eligibility.py)

* **WHAT:** `filter_candidates(candidates, profile)` drops plans whose `payment_methods_user_will_consider` or `max_installment_months` term gate fails, before simulation.
* **WHERE:** `src/affordai/decision/eligibility.py:filter_candidates`, docstring with full contract; called in `pipeline.py:decide_context` between `generate` and `simulate`.
* **WHY:** Preference must gate before ranking and before floor re-check (correct order: unsafe-but-preferred is kept to simulation then rejected, not silently dropped early).
* **INPUTS:** `list[Candidate]`, `profile` dict
* **OUTPUTS:** `list[Candidate]` filtered + reason notes per dropped candidate
* **AUTHORITY:** Deterministic allowlist check; LLM never filters.
* **FAILURE MODES:** Blank `max_installment_months` → installments ineligible; `partial` 5-cond failure → no partial candidates (0 occurrences in 250 rows, tested synthetically).
* **TEST COVERAGE:** `tests/regression/test_sections_15_21.py:test_eligibility_*` (3 tests: preference/term, keep-unsafe-but-preferred separation, wait needs full).
* **ALTERNATIVE DESIGN:** Rank first then filter (hides preference violations).
* **TRADE-OFF:** Extra filter pass before simulation saves simulating ineligible plans but requires correct ordering (generate → eligibility → simulate → rank).
* **REAL EXAMPLE:** `request_36` considers `full_payment` only → installments filtered out even though schedule exists; `wait` survives because `full_payment` allowed.
* **LIMITATION:** Eligibility is purely allowlist-based; no dynamic negotiation of preferences.

### Serializer (output/serializer.py, output/validator.py canonical ordering)

* **WHAT:** `decisions_to_rows` enforces exact 8-column order (`OUTPUT_COLUMNS`), `sorted-by-original_index`, duplicate-PK check, Decimal `quantize` to 2dp, date `YYYY-MM-DD`, plan `YYYY-MM-DD:amount` joined by `|` or `none`, `write_output_csv` QUOTE_MINIMAL with LF `\n`.
* **WHERE:** `src/affordai/output/serializer.py:EXACT_COLUMNS`, `decisions_to_rows`, `format_plan`, `format_date`, `write_output_csv`; `src/affordai/decision/decision.py:OUTPUT_COLUMNS` single source.
* **WHY:** Output CSV must be byte-identical across replays and match submission schema exactly (header `b'request_id,amount_safe_to_pay,...'`).
* **INPUTS:** `list[Decision]` + `home_by_request` dict
* **OUTPUTS:** CSV file on disk with 250+header rows in input order
* **AUTHORITY:** Pure derivation from `Decision`; no arithmetic, no LLM.
* **FAILURE MODES:** Duplicate request_id → ValueError; wrong column order → validator `OUTPUT-STRUCT` blocks submission.
* **TEST COVERAGE:** `tests/regression/test_sections_22_26.py:25.x` (8 tests: cols/order/one-row/escape/round-trip/dates/plan/no-recompute).
* **ALTERNATIVE DESIGN:** Let Python csv writer infer order from dict keys.
* **TRADE-OFF:** Explicit column tuple and sort is more verbose but guarantees `output.csv:1` header byte-matches `decision.py:34`.
* **REAL EXAMPLE:** `request_30` → installments plan serialized as `2026-04-06:268.74|2026-05-06:268.74|2026-06-05:268.74`, round-trip with comma/quote preserved.
* **LIMITATION:** No streaming writer for >10k rows; whole `decisions` sorted in memory (fine for 250).

### Observability and Tracing (observability/request_trace.py, observability/tracing.py, pipeline rtrace)

* **WHAT:** Per-request `RequestTrace(trace_id, original_row_index, facts, candidates, rejected_plans with reason_code, selected, status)` wired through `pipeline.run` + `_collect_evidence` + `_decide_safe`; global `Trace` for legacy events. Bounded `make_trace_id(run_id, request_id, index)`.
* **WHERE:** `src/affordai/observability/request_trace.py:RequestTrace`, `RequestTraceStore`, `make_trace_id`; `src/affordai/observability/tracing.py:Trace`; `src/affordai/pipeline.py` `rtrace` threading in `run` and `decide_context` + `_populate_rtrace`.
* **WHY:** Single-request inspection for a deterministic pipeline (no second service to query).
* **INPUTS:** `RequestContext` + intermediate state (registry, safe, earliest, candidates)
* **OUTPUTS:** In-memory `request_traces dict` consumable by `scripts/trace_request.py`; no file persisted by default (caller decides).
* **AUTHORITY:** Deterministic ids; never stores prompts/keys (`redact()`), never logs secrets.
* **FAILURE MODES:** Missing request_id → fallback trace with failure logged; trace never raises into pipeline.
* **TEST COVERAGE:** `tests/regression/test_sections_33_35.py` 30 tests (trace sections 10/10, determinism, output-row mapping).
* **ALTERNATIVE DESIGN:** External OTel/dashboard/DB.
* **TRADE-OFF:** In-process trace is minimal overhead (0 extra deps) but not a persistent observability backend; sufficient for 250-row audit.
* **REAL EXAMPLE:** `python scripts/trace_request.py --request request_30 --dataset dataset/official` emits JSON with facts, 3-leg installments, rejected 4 candidates with `DEADLINE_EXCEEDED` etc.
* **LIMITATION:** Traces live only for the `request_traces` run; `clean_room_run` subprocess does not persist them beyond `evaluation/local` if caller writes them.

## Q&A: Authority & Fallback

* **Deterministic core authority:** balances, income/expenses, minimum, amounts/dates, forecast, 90-day sim, decision rules, deadline, plan validity/ranking, final validation -- all deterministic (`finance/*`, `decision/*`, `output/validator`). LLM `!= financial authority` (proved via `tests/regression/test_sections_15_21.py:test_no_llm_or_clock_in_deterministic_core` grep for `propose_facts`/`openai`/`date.today` absence).
* **Fallback:** Per-request `pipeline._decide_safe` degrades to `not_affordable/none/0` preserving `safe/earliest` when derivable, never crashes batch (`tests/regression/test_guards.py:test_r6_per_request_fallback_never_crashes_batch`).

## Worked Examples

* **Normal (request allows full):** opening 20000/minimum 3000/requested 4000 -> `max_safe_today` 4000 -> `earliest` REQ -> candidates `full` safe -> `full` selected -> `affordable_now/full_payment/REQ:4000/REQ/none`
* **Ambiguous (message amend):** `Please update amount to 2500 for next month.` with `related_event_id e-am` -> `interpret` amend_amount 2500 -> `conflict_resolver.amended_amounts` -> `build_flows` re-maps -> re-simulates
* **Image-only (blank amount):** `event amount None` -> `resolve_images_for_event` finds linked PNG -> vision disabled -> `amount_unknown_evidence` UNKNOWN (never 0) -> plan must stay safe without it; E2 linkage clears 11 ev errors
* **Conflict (cancel vs amend same event):** `amend_amount 50` + `cancel e-2` -> `resolve` cancel rank 0 wins -> `cancelled_event_ids` includes e-2 -> `build_flows` drops event
* **Installment (exactness):** `opt_7` 3 payments `first 2025-01-10 freq 30 fee 200 total 3200` -> `expand_schedule` legs exact -> `Candidate` `option_id opt_7 total 3200` -> `validate_plans` re-derives totals incl fees -> ranking 6-tuple picks lowest `total` then `option_id`

## §38.2 Walkthroughs (all values LOCAL MEASUREMENT from `output.csv` + `dataset/official`, 2026-09-13)

Conventions: `simulate` = `finance/forecast.py:simulate`; floor = `closing >= minimum` every day of `[request_date, +89d]`; rank = `optimizer.rank_key` 6-tuple. Synthetic cases are labelled as such (engine proven by regression tests, 0 production occurrences).

### A. NORMAL — request_26 → affordable_now / full_payment
INPUT: `user_26`, `request_date 2025-08-03`, requested `15656000 IDR`, deadline `2025-10-07`, `allows_partial=false`. Profile: home `IDR`, balance covers request + floor.
→ DATA JOIN: `build_contexts` indexes user_26 → profile/events/options; `original_index` stamped.
→ EVIDENCE: deterministic `interpret` over its messages (no override facts).
→ STATE: `state.build` opening/minimum/requested + `timeline.build_flows` daily net.
→ FORECAST: `max_safe_today` = 15656000 (== requested); `earliest_full_date` = 2025-08-03.
→ CANDIDATES: `full` (2025-08-03:15656000) simulates ok; eligibility passes (user accepts full).
→ RANK → DECISION: `full` wins → `affordable_now/full_payment`, safe 15656000, earliest = request_date, changes none.
→ VALIDATE: structural + plan + consistency PASS.
OUTPUT ROW: `request_26,15656000,affordable_now,full_payment,2025-08-03:15656000,2025-08-03,none,"Requested 15656000 IDR on 2025-08-03: ..."`.

### B. IMAGE-ONLY AMOUNT — request_33 → blank stays UNKNOWN → not_affordable
INPUT: eval request with a blank-`amount` financial event linked from `images.csv` (`image_06` → request_33's blank event).
→ LINKAGE: `resolve_images_for_event(event_id, images, media_dir)` finds the PNG, `file_exists=true`.
→ EXTRACTION: no vendored vision backend → `propose_facts("image_amount",…)` returns `no-backend`, 0 facts, estimated-token record only.
→ UNKNOWN, NEVER ZERO: `amount_unknown_evidence` (confidence 0) recorded; `money.parse_amount` blank→None path; event contributes no cash flow.
→ DETERMINISTIC FINANCE: forecast + candidates run without the unknown amount; no candidate completes safely.
→ DECISION: `not_affordable/not_recommended`, safe 0, plan `none`, earliest empty.
WHY NOT ZERO: zero would fabricate a free expense (unsafe direction) or fake income; UNKNOWN forces the plan to prove safety without the fact. Proven by `test_s29_image_extraction_blank_never_zero` + 16↔16 bijection test.

### C. CONFLICTING EVIDENCE — synthetic cancel-vs-amend (engine: `test_p0_hardening.py:12-80`, 8 cases)
INPUT (synthetic): `amend_amount 50` + `cancel e-2` for the same event, different `sent_at`.
→ `interpret` emits two typed facts → `conflict_resolver.resolve` 3-pass stable sort: explicit cancel (rank 0) beats amend (rank 2); newer-wins and settled-over-estimate apply only within equal explicit rank.
→ `cancelled_event_ids` ∋ e-2 → `build_flows` drops the event → re-simulate → rank → decide.
LLM never reorders (`_method_rank` puts LLM last). Adversarial proof: `test_adv3031/3032` newer-wins + cancel>amend.

### D. PARTIAL PAYMENT — synthetic (0 production occurrences in the 250 rows; LOCAL MEASUREMENT of engine)
Gates in `payment_plans.generate` (all five required): request `allows_partial` AND user accepts `partial_payment` AND `0 < safe < requested` AND `earliest <= desired_completion_date` AND exact 2-leg shape `request_date:safe | earliest:(requested − safe)` summing to requested.
→ `filter_candidates` eligibility → `simulate` safety → rank → `rules.derive` maps partial ⇒ `affordable_with_plan` (never any other status).
Proven by `test_partial_exact_two_payment_shape` + `test_partial_gated_off` (3 gate rejections). No installment option match needed (unlike installments).

### E. INSTALLMENT — request_30 → affordable_with_plan / installments
INPUT: `user_30`, USD, requested `775.2`, `request_date 2026-04-06`, deadline `2026-06-06`, `allows_partial=false`, considers `partial_payment|installments`, min 900 / balance 3752.72. No messages (pure deterministic path).
→ STATE/FORECAST: safe today 738.16 (< requested, so full fails); single-payment scan never safe → earliest empty.
→ CANDIDATES: `installments` via `expand_schedule` exact match (3 legs `2026-04-06:268.74|2026-05-06:268.74|2026-06-05:268.74`, total 806.22 incl. fee); partial gated off (`allows_partial=false`); wait ineligible in effect (earliest empty).
→ SAFETY: each leg re-simulated, floor holds, completes 2026-06-05 ≤ deadline; term/preference gate passes.
→ DECISION: `affordable_with_plan/installments`, safe 738.16, earliest empty (capacity ≠ schedule completion — earliest measures ONE payment, installments complete via schedule).
OUTPUT ROW: `request_30,738.16,affordable_with_plan,installments,2026-04-06:268.74|2026-05-06:268.74|2026-06-05:268.74,,none,"..."`.

### F. WAIT — request_36 → affordable_later / wait
INPUT: `user_36`, USD, requested `3954`, `request_date 2026-07-03`, deadline `2026-09-15`, considers `full_payment` only. Evidence: `message_26` (2026-06-22, payroll: salary increase to USD 2988 from 2026-07-15).
→ EVIDENCE: deterministic `interpret` + `message_income.confirmed_series` (employer + confirm semantics + salary keywords; payroll ref `EMP-0026` alone never parses as an amount).
→ FORECAST: full unsafe today (safe 789.44 < 3954); forward scan first safe single-payment date = 2026-08-15 (future salary in flows).
→ CANDIDATES: `wait` = single future payment `2026-08-15:3954`; eligible (future-safe + user accepts full); completes ≤ deadline.
→ DECISION: `affordable_later/wait`, safe 789.44 (BEFORE changes, per contract), earliest 2026-08-15 > request_date.

### G. NOT AFFORDABLE — request_28 → not_affordable / not_recommended
INPUT: `user_28`, EUR, requested `1302.4`, `request_date 2024-06-07`, deadline `2024-08-15`, considers `full_payment`, min 1100 / balance 1789.4.
→ Every candidate rejected: full unsafe (safe 0), no eligible installment/partial path, wait impossible (earliest empty — never safe in window).
→ FALLBACK: `not_recommended`, plan `none`, changes `none`, earliest empty, safe 0 (`0 <= safe <= requested` holds).
→ Validator consistency: `not_affordable ⇔ not_recommended ⇔ plan none` PASS.
OUTPUT ROW: `request_28,0,not_affordable,not_recommended,none,,, "..."`.

## §38.3 Architecture defense (exact answers)

**Why deterministic core?** Financial arithmetic, dates, FX, simulation, validation, ranking require reproducible correctness: same input → same output (replay hash `d8386548517835c9` byte-identical). An LLM cannot guarantee `closing >= minimum` on all 90 days. Authority: `finance/*`, `decision/*`, `output/validator` (grep-proven LLM/clock-free).
**Why targeted AI?** Messages (`messages.csv`, multilingual, 215 rows) and receipt images (16 PNGs) carry semantics regex cannot fully cover (amend/cancel/confirm intent, pictured amounts). AI is used ONLY there, emitting typed facts with confidence.
**Why not multi-agent?** One request → one deterministic path has no decomposable scoring subtask: evidence interpretation feeds a single ledger; extra agents add nondeterminism, token cost, and failure surface with no measured accuracy win (ablation rule: keep only on measured wins; E0→E2 deltas documented, E3–E7 instrumented).
**Why no LLM arithmetic?** Safety-critical and exact: Decimal floor search, FX direction, fee-inclusive totals. LLM output is unvalidated text until `_validate_proposal` + registry + re-simulation prove it. The pipeline drops any non-conforming proposal.
**How 90-day safety works:** `temporal.forecast_end = request_date + 89` (inclusive 90 days); `timeline.build_flows` maps every flow to settlement dates; `forecast.simulate(state, payments, changes)` walks the daily ledger and returns `ok=False` on the first day `closing < minimum` or completion past deadline. `max_safe_today` binary-searches the largest today-payment keeping `ok=True`; `earliest_full_date` scans forward for the first single-payment `ok=True` day.
**How evidence is grounded:** source row → `interpret`/`resolve_images_for_event`/`propose_facts` → `Evidence` with full provenance (`source_type/source_id/request_id/user_id/event_id/message_id/image_id/raw/normalized/confidence/method/sent_at`) → `EvidenceRegistry.add` (IDs exist + ownership + confidence range) → `conflict_resolver` precedence → deterministic use. Unsupported evidence never enters decisions (rejections recorded).
**How conflicts are resolved:** fixed order — (1) explicit cancel/settle/amend (2) newer same-source `sent_at` descending (3) settled over estimate (4) safer interpretation + deterministic-over-LLM method rank + lexical tiebreak. Implemented as 3-pass stable sort in `conflict_resolver.resolve`; LLM cannot reorder.
**How validation protects output:** six layers (spec §9 / architecture doc): input → evidence → financial invariant → plan → decision → output gate. `scripts/validate_output.py` exits 1 on any hard error, blocking submission; 13/13 mutation controls rejected; full 250-row run PASS.

## Design rationale per component group (alternative / trade-off / limitation)

- **Ingestion + joins (`ingestion/*`, `pipeline.build_contexts`):** alternative = pandas-merge one-liners; rejected because silent row duplication breaks row identity (prior Orchestrate failure). Trade-off: more code for explicit `original_index` preservation + `JoinIntegrityIssue` audit. Limitation: dual-layout resolver covers `dataset/` vs `dataset/official/` only.
- **Message interpreter (regex-first):** alternative = LLM-first extraction; rejected (cost × 215 messages, nondeterminism). Trade-off: regex misses novel phrasing → covered by selective `needs_llm_for_messages` + `propose_facts`. Limitation: 20-char heuristic + salary-keyword list are tuned, not proven complete (INFERENCE).
- **Image path (linkage-first):** alternative = run vision on all 16 images blindly; rejected (cost, no backend vendored). Trade-off: UNKNOWN-safe blanks reduce recall of true amounts. Limitation: without a vision backend, pictured amounts never resolve (documented, never zeroed).
- **Conflict resolver (fixed precedence):** alternative = recency-only or LLM-judged; rejected (cancel must beat newer amend). Trade-off: rigid order may mishandle genuinely ambiguous cases → safest interpretation rule + fallback. Limitation: 4-rule order is Tier-1-derived, not officially published (INFERENCE, documented).
- **Forecast (daily loop + binary search):** alternative = closed-form balance equation; rejected (recurrence clamping + conditional flows resist closed form). Trade-off: ~8ms/req compute (84% in `decide`, measured) for exactness. Limitation: 31d/month installment approximation + recurrence thresholds UNPROVEN.
- **Ranking (6-tuple key):** alternative = weighted scoring; rejected (ties unexplainable, irreproducible). Trade-off: lexicographic order can prefer a slightly costlier on-time plan — intended (deadline first per contract).
- **Explanation (template over Decision):** alternative = free-form LLM summary; rejected (hallucinated amounts/dates). Trade-off: stilted prose for grounding (`validate` 250/250). Limitation: templates don't localize multilingual input.
- **Token accounting (`usage.py` + records):** alternative = provider dashboard only; rejected (must attribute per-request/per-model locally). Trade-off: local chars/4 estimates are coarse → labelled `estimated`, provider values win when present. Limitation: cost UNKNOWN without verified `PRICING`.
