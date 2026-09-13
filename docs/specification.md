# Specification — AffordAI (HackerRank Orchestrate September 2026 — Buy or Wait?)

Source of truth: official `problem_statement.md` + `AGENTS.md §6` from
`upstream/main` (fetched, never merged). This file mirrors that contract for implementation.
Where prose and data disagree, the data + samples govern after documentation.

## 1. Problem

For each row in `dataset/official/requests.csv`, decide whether the user can safely
afford the requested commitment, considering balance, minimum balance, essential/
recurring/pending/confirmed flows, payment options, preferences, priorities,
flexible-spending willingness, messages, images, history, FX, and desired completion date.
The recommendation must be safe across the 90-day forecast and personalized.

## 2. Inputs (`dataset/official/` locally; `dataset/` upstream — READ-ONLY)

| File | Grain | Joins |
|---|---|---|
| `requests.csv` (250 eval rows) | one row per `request_id` | `request_id`, `user_id` |
| `sample_requests.csv` (25 solved) | format/decision-style examples, NOT eval labels | same + completed outputs |
| `financial_profiles.csv` | one row per `user_id` | `user_id` |
| `financial_events.csv` | txns: historical/pending/scheduled/settled/failed/cancelled/non-cash | `user_id`, `event_id`, `linked_event_id` → earlier event same lifecycle |
| `request_payment_options.csv` | 2–4 options per `request_id` | `request_id`, `payment_option_id` |
| `exchange_rates.csv` | fixed dated rates | rate date + `from_currency→to_currency` |
| `messages.csv` | user/request/event evidence | `user_id`, `request_id`, `related_event_id` (only when 1:1 to an event row; blank = no 1:1 row) |
| `images.csv` + `media/images/<image_id>.png` | linked evidence | `user_id`, `request_id`, `related_event_id` |
| `output.csv` (template) | blank submission shape | — |

> **Path note (Phase 4 verified):** upstream Tier-1 contract is `dataset/requests.csv` (see `git ls-tree upstream/main` + `problem_statement.md Files provided`). Local fork uses `dataset/official/requests.csv` (`git ls-files -- dataset`). Both layouts are supported: `src/affordai/pipeline.py:_resolve_dataset_path` tries `dataset_dir/filename` then `dataset_dir/official/filename` (and reverse). Evaluator may provide either layout; do not hardcode one prefix.

Request fields: `request_id, user_id, request_date, request_type
(purchase|travel|education|family_transfer|debt_repayment|investment|housing|emergency_expense|other),
requested_amount, desired_completion_date, allows_partial_payment (bool), request_text`.
Profile fields include `home_currency (INR|ZAR|IDR|USD|EUR)`, `current_available_balance`,
`minimum_balance_to_keep`, `financial_priorities`, `expense_categories_to_protect`,
`expense_categories_user_is_willing_to_reduce/_stop`, `payment_methods_user_will_consider`,
`max_installment_months` (blank = will not consider installments).
Payment-option fields: `payment_option_id, request_id, payment_method, payment_amount, number_of_payments,
first_payment_date, payment_frequency_days, financing_fee, total_payable_amount`.
All dates `YYYY-MM-DD`. All money I/O in `home_currency`; convert foreign cash events with
the rate row for the event's settlement date and stated direction — **UNPROVEN assumption A1**: latest row **on or before** settlement for the **exact directed pair** (no inverse synthesis); exact match holds for all 140 foreign cash events in this dataset but off-cycle settlement would require fallback (see `evaluation/reports/data_inventory.md §6` and `docs/data-model.md`).

## 3. Required output (`output.csv`, root)

Exact columns in exact order, one row per eval request, sorted by input order:

```text
request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation
```

- `amount_safe_to_pay`: max safe to pay on `request_date` BEFORE optional spending changes,
  protecting essentials + minimum. Invariant: `0 <= amount_safe_to_pay <= requested_amount`.
- `affordability_status ∈ {affordable_now, affordable_with_plan, affordable_later, not_affordable}`:
  - `affordable_now`: full amount safe on `request_date` AND user accepts `full_payment`.
  - `affordable_with_plan`: full request completed via partial schedule, installments, or permitted spending changes.
  - `affordable_later`: full amount becomes safe later (within forecast).
  - `not_affordable`: cannot complete safely within forecast.
  - `affordable_now ⇒ earliest_date_for_full_payment == request_date`.
  - Empty `earliest_date` ⇔ full payment never safe within forecast.
- `recommended_payment_method ∈ {full_payment, partial_payment, installments, wait, not_recommended}`.
- `payment_plan`: chronological `YYYY-MM-DD:amount` joined by `|`, or `none`.
  - Installments MUST exactly match one supplied payment option (dates + amounts + count).
  - `partial_payment` additionally requires `affordability_status == affordable_with_plan`
    AND request allows partial AND user accepts it AND `0 < safe < requested`
    AND `earliest_date <= desired_completion_date`; exactly two payments:
    `request_date:safe | earliest_date:(requested − safe)`, summing to `requested`.
    Unlike installments, partial needs NO matching payment option.
- `earliest_date_for_full_payment`: first date full amount passes the safety check as ONE
  payment WITHOUT optional spending changes. Independent of method preferences
  (may equal `request_date` even when installments are recommended because user excludes full).
- `spending_changes_needed`: `none` or ≤3 `stop:<event_id> | reduce_to:<event_id>:<new_amount>`
  joined by `|`. Only flexible recurring expenses in user-permitted categories.
  Stop+reduce on the SAME event are mutually exclusive.
- `decision_explanation`: short, grounded in validated facts only.

## 4. 90-day safety check (central invariant)

Forecast 90 days from `request_date` with recurring income/expenses, confirmed future
payments, relevant message/image adjustments. A plan is safe ONLY if:
`closing_balance >= minimum_balance_to_keep` after EVERY projected essential expense
and plan payment; the request completes by `desired_completion_date`.
Ignore: pending credits/bonuses/commissions/refunds/lottery/investment gains until settled,
failed/cancelled transactions, duplicate records, unrealized investment value.
Reserve pending debits. Count confirmed salary only on settlement date.
Detect recurrence only when history supports it; forecast essential variable spending conservatively.
Do not invent income/expenses/options/facts. Investments = affordability of contributions only
(no price prediction, no security advice).

## 5. Choosing between safe plans

Eligibility: `full_payment|partial_payment|installments` eligible only if listed in
`payment_methods_user_will_consider` (plus `max_installment_months` for installments).
`wait` eligible only if full becomes safe later AND user accepts `full_payment`.
`not_recommended` = fallback when no safe eligible plan exists.
Rank safe eligible plans:
1. complete by `desired_completion_date` 2. no spending changes 3. minimize total paid
4. earlier start 5. fewer payments 6. lowest `payment_option_id`.

## 6. Evidence rules

- Blank event `amount` → find `event_id` as `related_event_id` in `images.csv` → extract
  from image. NEVER treat blank as zero.
- Messages/images are untrusted data: may clarify/amend/cancel/delay/confirm facts;
  embedded instructions NEVER override these rules.
- Conflict precedence: (1) explicit cancellation/settlement/amendment (2) newer record
  same source (3) settled over estimate/forecast (4) financially safer interpretation.

## 7. Implementation assumptions (VERIFIED vs UNPROVEN) — Phase 4 audited 2026-09-13

- VERIFIED from data (reproducible, see `evaluation/reports/data_inventory.md` + `dataset_regression_snapshot.json`): 16 blank `financial_events.amount` ↔ 16 `images.csv:related_event_id` ↔ 16 PNGs 1:1:1 (hashes `f94255ba…` etc.); 5 directed FX pairs `USD→INR/IDR/EUR, EUR→USD/ZAR` (134 rows, 39 dates `2023-10-15→2026-11-15` + `2025-10-01`); `sent_at` ISO `YYYY-MM-DDTHH:MM:SSZ`; preference lists `|`-split; 90-day window `[request_date, request_date+89]` inclusive (spec §4); money bare-integer or 2dp (IDR `15952906.67` observed); all PKs unique, 0 orphans eval-partition (see `evaluation/reports/join_integrity.md`).
- IMPLEMENTED (E0, defensible, residual risk noted): income counts only
  scheduled/settled-future rows plus narrowly message-confirmed salary
  (employer + confirm semantics + salary keywords; deny-first; routine-amount
  fallback); history salary is NOT projected (sample request_05 decisive).
  Expense/subscription recurrence via monthly/weekly cadence plus flexible
  same-description repetition (≥2, gap ≥7d); debt/investment obligations never
  inferred; installment term ≈ span_days ≤ months×31 (31d approximation — **UNPROVEN**); pending debits reserved
  at request_date; blank settlement_date falls back to event_date (10 `unrealized` rows, then ignored).
- UNPROVEN (explicit, not guessed): **A1 FX** latest-on-or-before exact pair (holds 140/140 today, off-cycle would fallback); 90-day inclusive bound (`+89` vs `+90`); `max_installment_months` semantics (31d/month); grocery/transport medians vs official conservative
  estimates (±3% calibration noise); variable-spending conservatism rule;
  salary-day tie-breaks; prize/ambiguous-credit handling; rent-bump and
  new-deduction messages (ignored, documented); earliest==deadline
  coincidences in 2 sample rows; `streaming`/`gym` dual willingness (41 profiles) — per-event exclusive only.

## 8. Submission

`code.zip` (runnable code + prompts/config + README + `evaluation/`), root `output.csv`
(250 rows + header), `chat_transcript (log.txt)`.
`code.zip` MUST contain `evaluation/usage_report.md`: provider(s)/model(s), calls,
input/output/total/avg-per-request tokens, est. total + per-request cost for the FINAL
full-dataset run (per-model + overall). No secrets anywhere.
Solution: runnable from terminal, reads `dataset/`, deterministic where possible,
no organizer-only files, no hardcoded labels.

## 9. Failure semantics (what happens when things go wrong)

| Failure | Detection | Behavior |
|---|---|---|
| Invalid input (bad schema/type/duplicate PK) | ingestion validators, `_dedupe_by_key`, identity checks | `DatasetError` at load; per-request fallback, never a crash of the batch |
| Missing evidence (blank amount, no linked image, unreadable file) | `resolve_images_for_event` `file_exists=false` | UNKNOWN marker (`amount_unknown_evidence`, confidence 0); blank is NEVER zero; plan must stay safe without it |
| Invalid AI output (bad JSON/schema/confidence/ownership) | `_validate_proposal` strict gate + `min_confidence` + `EvidenceRegistry.add` | proposal dropped; deterministic facts still apply |
| Unavailable model (timeout/429/5xx/no backend) | `call_with_retry` retry taxonomy, `FAILURE_MATRIX` | bounded retries only for transient errors, then `no-backend`/empty fallback; 0 facts added |
| Impossible plan (floor breach/deadline miss/preference conflict) | `simulate()` + `filter_candidates` | candidate rejected; `not_recommended` fallback when none survive |
| Per-request exception (any unexpected error) | `pipeline.run` try/except per context | `_decide_safe`: `not_affordable/not_recommended/none/0`, preserving derivable safe/earliest; batch continues |
| Validation failure (any hard error) | `output/validator.py` + `scripts/validate_output.py` | exit 1 — blocks submission; file still written for inspection |

Missing evidence is NEVER affirmative evidence. Failed validation is NEVER a
successful decision. Cross-request evidence is NEVER accepted (`check_batch_safe`
+ registry ownership). Deadlines are inclusive (`meets_deadline`: completion <=
desired date; deadline day counts, day after does not).

## 10. Prohibited behavior (AI must NEVER decide)

Arithmetic, date math, FX conversion, 90-day simulation, safe-amount search,
earliest-date scan, plan arithmetic/totals, deadline/minimum validation,
eligibility, ranking/tie-breaks, final numerical decisions, schema enforcement,
conflict precedence. AI proposes candidate typed facts; deterministic code proves
safety. Any AI output touching these areas is dropped by validation. Proven by
`tests/regression/test_sections_15_21.py::test_no_llm_or_clock_in_deterministic_core`
(`finance/*`, `decision/*` contain zero LLM/clock/random imports).
