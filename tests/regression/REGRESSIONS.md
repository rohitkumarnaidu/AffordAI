# Regression Registry (Section 29.1) -- permanent failure-capture record.

Lifecycle: FAILURE -> capture -> expected -> actual -> root cause -> general
rule -> targeted fix -> regression test -> nearby-case test -> full suite ->
report. Never fix only the visible example. Never delete records.

Format per entry: ID | category | input | expected | actual | root cause |
general rule | fix | test | detected-by | severity | status.

---

## S29-R01 -- partial gate shape (2026-09-13, session 27-30)

- Category: partial payment
- Input: synthetic FinancialState opening 8000 / minimum 2000 / requested 4500
  (+6000 inflow) fed to payment_plans.generate(..., allows_partial=True)
- Expected (test author): exactly 1 partial candidate
- Actual: 0 partial candidates
- Root cause: TEST BUG, not production bug. safe == requested (6000 capacity
  covers 4500), so generation correctly refuses partial (needs
  0 < safe < requested). Author assumed inflow timing would constrain today.
- General rule: regression states for partial MUST assert the
  0 < safe < requested precondition explicitly (helper `_tight_state`).
- Fix: test uses opening 5000 / minimum 2000 (safe 3000 < 4500).
- Test: tests/regression/test_sections_27_30_regression.py::test_s29_wrong_payment_partial_sums_to_requested
  + test_s29_partial_payment_gate
- Nearby: test_s29_minimum_balance_floor_exact (bounds), adversarial partial
  allowed/disallowed (30.5).
- Detected-by: new regression suite run. Severity: low (test-only).
- Status: FIXED (test corrected; production behavior confirmed correct).

## S29-R02 -- earliest minimality state (2026-09-13, session 27-30)

- Category: wrong date
- Input: opening 9000 / minimum 1500 / requested 7000 (+9000 inflow 2025-05-03)
- Expected: earliest > request_date
- Actual: earliest == request_date (9000-1500=7500 covers 7000 today)
- Root cause: TEST BUG (same class as S29-R01) -- capacity covered request today.
- General rule: earliest-minimality states must have safe < requested today.
- Fix: opening 5000 (safe 3500 < 7000); earliest 2025-05-03 verified minimal
  by day-by-day unsafe loop.
- Test: test_s29_wrong_date_earliest_minimal. Detected-by: regression run.
  Severity: low (test-only). Status: FIXED.

## S29-R03 -- RateTable.get_rate return type (2026-09-13, session 27-30)

- Category: currency
- Input: get_rate("USD","INR",2025-03-15)
- Expected (test author): Decimal("83")
- Actual: RateLookup object with .rate == Decimal("83") (correct value, richer type)
- Root cause: TEST BUG -- author assumed Decimal return; API returns a
  provenance-carrying RateLookup (source/target/settlement/rate/rate_id).
- General rule: assert on `.rate` for value + keep trace fields for provenance.
- Fix: test asserts `.rate`; convert_to_home value/trace assertions unchanged.
- Test: test_s29_currency_dated_directed_rate. Detected-by: regression run.
  Severity: low (test-only). Status: FIXED.

## S29-R04 -- registry checks id FIELDS not source_id (2026-09-13, session 27-30)

- Category: evidence mismatch
- Input: Evidence("message","mX",...) with message_id=None, correct request/user
- Expected (test author): rejected as unknown id
- Actual: admitted (ownership/kind/method/confidence all valid; the registry
  validates message_id/event_id/image_id fields, not source_id)
- Root cause: TEST BUG -- author constructed evidence without the checked field.
  Production behavior is correct and matches evidence_registry.add contract.
- General rule: mismatch tests must populate the id FIELD the registry checks
  (message_id/event_id/image_id) plus wrong-request/wrong-user ownership cases.
- Fix: test sets message_id="mX", adds unknown event_id case; keeps ownership cases.
- Test: test_s29_evidence_mismatch_rejected. Detected-by: regression run.
  Severity: low (test-only). Status: FIXED.

## S29-R05 -- E0/E1 evidence gap on masked images (2026-09-13, ablation)

- Category: evidence mismatch (ablation finding, production NOT affected)
- Input: full 250 requests with images masked (E0/E1 input configurations)
- Expected: evidence validator green
- Actual: 11 OUTPUT-EVIDENCE-002 errors (missing-image:<event> refs have no
  valid image id when images are masked)
- Root cause: input-masking artifact -- E0/E1 remove the image rows that make
  blank-amount UNKNOWN refs valid. Production (E2) links all 16 images: 0 errors.
- General rule: ablation E0/E1 evidence errors are a measured cost of dropping
  the image channel, documented as the E2-minus-E1 delta (11 -> 0), not a bug.
- Fix: none to production; documented in evaluation/reports/ablation_results.md.
- Test: scripts/run_ablation.py E1/E2 evidence_errors. Detected-by: ablation run.
  Severity: info (measurement). Status: DOCUMENTED.

---

## Prior registry (pre-existing suites; tests, not re-listed here)

- R1 earliest-with-not_affordable, R2 row identity, R3 payroll refs,
  R4 pipe-split, R5 sent_at ordering, R6 per-request fallback
  (tests/regression/test_guards.py).
- P0 hardening 12 cases: conflict 4-rule, protected spending, message
  preference, image blank!=0, injection inertness
  (tests/regression/test_p0_hardening.py).
- Sections 15-21 gap pins: safe bounds/monotonicity, earliest minimality,
  partial/installment/wait shapes, eligibility separation, optimizer ties,
  rules mapping, LLM/clock-free core (tests/regression/test_sections_15_21.py).
