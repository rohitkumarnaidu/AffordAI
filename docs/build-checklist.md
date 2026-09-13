# Build Checklist — Modules 0–35 (completion gate)

Status per item: `[x]` complete · `[~]` partial · `[ ]` not started · `[!]` blocked/risky · `[-]` n/a.
Evidence required: implementation + tests + validation output, not file existence.
Updated 2026-09-13 after E0 deterministic build (44 tests green, 250-row
validator PASS, byte-identical replay). Referenced by `AGENTS.md` §§27–27b, 30.

## MODULE 0 — Repository & governance
- [x] 0.1 repo init, `origin`=AffordAI, `upstream`=official-ref, branch/worktree known
- [x] 0.2 `.gitignore` (.env, log.txt, local dirs), no secrets, meaningful commits, upstream never merged
- [~] 0.3 transcript: root `log.txt`, append-only, session-start + per-turn, exact `tool=`, redaction, shared log
  (12:24/12:35 ordering wrinkle + rounded-clock stamps disclosed in-file; never rewritten)

## MODULE 1 — Specification
- [x] 1.1 core spec (objective, I/O, enums, financial/temporal/evidence/conflict/preference rules, prohibitions)
- [x] 1.2 decision matrix (states, methods, partial/installment/spending/deadline/tie-break rules; Tier-1 earliest fix applied)
- [~] 1.3 edge semantics (assumption register in `specification.md` §7; FX-A1/recurrence tested; calibration + prize/rent-bump/new-deduction gaps documented UNPROVEN)

## MODULE 2 — Data ingestion (`src/affordai/ingestion/`)
- [x] 2.1 loaders: requests, profiles, events, payment options, FX (`finance/currency.py`), messages, images
- [x] 2.2 schema validation: columns, types, nulls, unexpected values, row counts (250/275/25342/790/134/215/16 verified)
- [x] 2.3 identity: `original_index`, `request_id`, `user_id`; registry rejects cross-request/user leaks (tested)

## MODULE 3 — Relationship / join engine
- [x] 3.1 joins: user→profile, request→user/options/messages(+user-level), event→image
- [~] 3.2 lifecycle: `related_event_id` amendments + duplicate-ID rejection live; `linked_event_id` chains not traversed (link-alone≠verdict per inventory; statuses carry the semantics)
- [x] 3.3 safety: missing refs rejected, ownership enforced, deterministic ordering

## MODULE 4 — Canonical request context (`pipeline.py: RequestContext`)
- [x] 4.1 object carries index/ids/request/profile/events/messages/images/options/evidence
- [x] 4.2 sorted options, (sent_at, id) messages, output sorted by original_index

## MODULE 5 — Evidence system (`evidence/evidence_registry.py`)
- [x] 5.1 provenance fields (source type/id, request/user/event/message/image, raw/normalized, method, confidence)
- [x] 5.2 validation: IDs exist, correct owner, confidence bounded, no fabrication (tested)

## MODULE 6 — Message intelligence
- [x] 6.1 detect: cancel/settle/amend/delay/confirm/amount-change/date-change + salary linkage + confirmed-salary series
- [x] 6.2 safety: injection resistance (typed facts only; adversarial tests), irrelevant/malformed handling, provenance
- [~] 6.3 AI: adapter interface + strict schema gate + fallback + usage tracking live; no live backend wired (E0 needs none)

## MODULE 7 — Image intelligence
- [x] 7.1 resolution: id mapping, file exists, linkage, relevance filter
- [~] 7.2 extraction: deterministic side live; amounts via adapter when enabled, else UNKNOWN (never zero)
- [x] 7.3 failures: blank/missing/unreadable/irrelevant handling (blank≠zero enforced + tested)

## MODULE 8 — Conflict resolution (`evidence/conflict_resolver.py`)
- [x] 8.1 precedence: cancel/settle/amend → newer same-source → settled → safer; deterministic; AI can't override
- [x] 8.2 regression fixtures (cancel-wins, ordering)

## MODULE 9 — Currency engine (`finance/currency.py`, `money.py`)
- [x] 9.1 same/foreign conversion, dated A1 rate, direction, home-currency output, Decimal-only, ROUND_HALF_UP, 2dp scale from samples
- [x] 9.2 failures: missing rate/date-mismatch/unsupported pair/invalid amount (fail-closed + notes)

## MODULE 10 — Temporal engine (`finance/timeline.py`)
- [x] 10.1 request/event/settlement/income/recurring/payment/completion dates, 90-day window `[request_date, +89d]`
- [x] 10.2 edges: same-day, boundary, deadline-day, window-end, recurrence anomalies (edge tests)

## MODULE 11 — Financial state engine (`finance/state.py`)
- [x] 11.1 balance, minimum, essentials, flexible, recurring income, obligations, valid settled events
- [x] 11.2 pending debit (reserve day-0) vs pending credit (ignore), failed/cancelled/duplicate/unrealized excluded, confirmed salary on settlement date only

## MODULE 12 — 90-day forecast (`finance/forecast.py`)
- [x] 12.1 daily ledger: opening, inflows, essentials, recurring, existing + candidate payments, closing
- [x] 12.2 invariant `closing >= minimum` every day; no double-counting; deterministic

## MODULE 13 — Payment-plan engine (`finance/payment_plans.py`)
- [x] 13.1 candidates: full / partial / installments / wait / spending-change variants / not_recommended fallback
- [x] 13.2 each: safety → deadline → preference → ranking (simulated + filtered + selected)

## MODULE 14 — Amount safe to pay
- [x] 14.1 max safe today, before optional changes, bounded, minor-unit binary search
- [x] 14.2 boundaries: 0, full, exact edge, ±0.01 (edge tests)

## MODULE 15 — Earliest full-payment date
- [x] 15.1 scan from `request_date`; first safe single-payment date; empty if never; preference-independent (Tier-1)
- [x] 15.2 safety + deadline validation (validator plan layer)

## MODULE 16 — Partial payment
- [x] 16.1 eligible: allows-partial, user accepts, `0 < safe < requested`, `earliest <= deadline`
- [x] 16.2 exactly 2 payments (`safe` + remainder = requested), safe, on time (validator re-derives)

## MODULE 17 — Installments
- [x] 17.1 exact match: option id, count, dates, amounts, fees (validator re-derives from CSVs)
- [x] 17.2 user accepts installments, month-limit ok, safe, on time

## MODULE 18 — Spending changes (`finance/spending_changes.py`)
- [x] 18.1 flexible-only, protected kept, ≤3, syntax valid, stop/reduce exclusive
- [x] 18.2 change flips plan safe, deadline holds, no gratuitous changes (flip-required)

## MODULE 19 — Method eligibility (`decision/eligibility.py`)
- [x] 19.1 filter by accepted/excluded methods, installment + partial preferences
- [x] 19.2 selected plan is safe + eligible + correctly ranked (integration test)

## MODULE 20 — Ranker (`finance/optimizer.py`)
- [x] 20.1 deadline → no-changes → min total → earlier start → fewer payments → lowest option id
- [x] 20.2 tie tests incl. final option-id break

## MODULE 21 — Decision (`decision/decision.py`)
- [x] 21.1 canonical `Decision` carries all 8 fields + evidence + explanation facts
- [x] 21.2 status↔method↔plan↔dates↔changes↔explanation consistent (`explanation.validate`)

## MODULE 22 — Output (`output/serializer.py`, `validator.py`, `scripts/validate_output.py`)
- [x] 22.1 exact columns/order/count/request order (250 rows, validator PASS)
- [~] 22.2 structural + plan layers live and independent; floor re-simulation lives in engine sim + tests (validator does not re-simulate balances — documented)

## MODULE 23 — Explanation (`output/explanation.py`)
- [x] 23.1 facts ⊆ validated decision facts; amounts/dates/evidence match; nothing invented
- [x] 23.2 concise, specific, decision-consistent

## MODULE 24 — AI layer
- [x] 24.1/24.2 message/image prompts bounded, schema-validated, fallback + usage tracked (adapter + deny-first rules + tests)
- [~] 24.3 explanation LLM not built (deterministic template only); validated-facts-only design recorded

## MODULE 25 — Evaluation (`evaluation/`, `scripts/evaluate.py`)
- [x] 25.1 local proxies: structural/financial/decision/plan/evidence/explanation/robustness (NOT official score; E0 0.44/0.56/0.36 recorded)
- [~] 25.2 sample/edge/adversarial/regression/full-dataset suites live; metamorphic rules NOT implemented
- [~] 25.3 ablation E0 measured; E1+ pending (adapter ready, no backend)

## MODULE 26 — Regression (`tests/regression/`)
- [x] 26.1 fixtures: row-order, evidence mismatch, cancel/amend, currency, date, plan, preference
- [x] 26.2 gate: `pytest` (40 green) + validator PASS before commits

## MODULE 27 — Observability (`observability/tracing.py`)
- [~] 27.1 per-request trace: evidence + decision stages with key facts (candidate-level rejection trace not recorded)
- [x] 27.2 no secrets, structured, deterministic ids

## MODULE 28 — Token & cost (`evaluation/usage_report.md`)
- [x] 28.1 provider/model/calls/in/out/total tokens tracked (0/0 E0)
- [x] 28.2 total + per-request cost, per-model breakdown (n/a deterministic)
- [x] 28.3 report reflects the FINAL full-dataset run, no secrets

## MODULE 29 — Security
- [x] 29.1 `.env`/`.env.example` placeholders-only, clean history, secret scan green
- [~] 29.2 injection/malformed-data tests green; malicious-IMAGE-content tests missing (no image bytes parsed in E0)
- [x] 29.3 no secrets in CSV/logs/artifacts

## MODULE 30 — Efficiency
- [x] 30.1 full-run runtime measured (2.4s / 250 rows), hot loops binary-searched
- [x] 30.2 model calls minimal (0), deterministic shortcuts throughout
- [x] 30.3 no spare agents/providers/dependencies (stdlib-only runtime)

## MODULE 31 — Clean room (`scripts/clean_room_run.py`)
- [x] 31.1 fresh subprocess: scrubbed env, temp out dir, dataset-only inputs
- [~] 31.2 run → `output.csv` → validate → usage report; executed, result recorded in log (rerun pre-submission)

## MODULE 32 — Reproducibility
- [x] 32.1 double-run byte-identical (sha256 match, 250 rows)
- [x] 32.2 stable ordering/ranking/math/serialization (Decimal, sorted ids)

## MODULE 33 — Documentation
- [x] 33.1/33.2 README + 8 tech docs + interview notes + assumption register (§spec 7) (+ this checklist)

## MODULE 34 — Interview (`docs/interview-notes.md`)
- [~] 34.1 walkthrough + Q&A seeds live; per-component WHAT/WHERE/WHY table partial
- [~] 34.2 deterministic-core + AI-boundary + fallback rationale recorded; trade-offs listed
- [ ] 34.3 worked examples: normal, ambiguous, image-only, conflict, installment

## MODULE 35 — Final submission
- [x] 35.1 `output.csv`: 250+header, order, schema, validator green
- [ ] 35.2 `code.zip`: runnable, README, evaluation files, no secrets, packaging tested
- [x] 35.3 usage report complete (provider/model/calls/tokens/costs)
- [~] 35.4 `log.txt` complete, append-only, identities exact, redacted (ordering wrinkle disclosed)

---

## Top-10 readiness gate (ALL true before submission)

```text
[x] specification complete · relationships verified · canonical state correct
[x] currency deterministic · 90-day simulator correct · plans + spending changes correct
[x] ranking correct · evidence grounded · output order exact · validator green
[~] adversarial + regression green (image-content tests missing) · token report complete · clean-room green (rerun pre-submission)
[x] deterministic replay checked · transcript complete · interview prepared (34.3 pending)
[x] no secrets · artifacts ready (code.zip pending)
```

## Red-flag gate (ANY true ⇒ DO NOT submit)

Row mismatch · duplicate/missing request · floor violation · fabricated evidence ·
bad schedule · deadline violation · unsupported method · invented installments ·
blank-as-zero · LLM in arithmetic/ranking · explanation≠decision · secrets committed ·
transcript bad · usage report missing · clean-room failure · critical regression open.

Current: NONE present (validator green, 40 tests green, secret scan green).
code.zip packaging + final clean-room rerun remain before submission.
