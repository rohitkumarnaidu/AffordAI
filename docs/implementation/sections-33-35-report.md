# Sections 33–35 Implementation Report — Observability, Reliability, Performance

Date: 2026-09-13 (session 16:58–17:40 IST; deadline 18:00 IST)
Author: opencode session (implementation) + concurrent verification session (commits 2291594, dcceb53)
Status: **GO** (all critical items PASS with execution evidence)

> Labels used: LOCAL MEASUREMENT = actually measured on this machine;
> INFERENCE = reasoned, not measured; UNKNOWN = could not be verified.

## Executive Summary

All 8 checklist groups across §§33–35 are PASS. No new engines, agents,
providers, or dependencies were added. Work reused §§27–32 infrastructure
(Trace, redact, llm_adapter, UsageReport, validator) and extended it only
where the gap analysis proved insufficiency (structured 10-section trace,
429/5xx retry taxonomy, indexed joins, benchmark + trace CLIs).

Overall: **GO**

## Gap matrix (pre-implementation → post)

| Item | Pre-existing | Gap | Change |
|---|---|---|---|
| 33.1 request trace (10 sections) | Trace with 2 event types only | 7/10 sections missing | `observability/request_trace.py` + `pipeline._populate_rtrace` |
| 33.2 trace integrity | request-id preserved; redaction | no trace_id, no CLI | `make_trace_id`, `scripts/trace_request.py` |
| 34.1 7 failure modes | Timeout/invalid-JSON covered | 429/5xx not typed | `RateLimitError`, `ProviderError`, `FAILURE_MATRIX` |
| 34.2 fallback | adapter + pipeline fallbacks | fallback reasons not in trace | `rtrace.failures`, `log_failure`, fallback final_decision |
| 34.3 retry | bounded transient-only | no backoff schedule, implicit policy | `backoff_for_attempt`, RETRYABLE/NON_RETRYABLE, `backoff_s` record |
| 35.1 runtime | wall time only (2.5s) | no stage breakdown; O(R·M) scans | `scripts/benchmark.py`; indexed joins |
| 35.2 AI perf | selective/minimized, cache N/A | unmeasured claim | measured: 0 calls, 16/16/11 image stats, cache empty |
| 35.3 competition time | none | no written strategy | §35.3 below |

## Section 33 — Observability: all PASS

- 33.1 request trace: PASS — `RequestTrace` (10 sections) populated for
  every request in `pipeline.run` when `request_traces` supplied; harness
  threads it through. Evidence: `tests/regression/test_sections_33_35.py`
  (13 trace tests) + 4 real traces in `evaluation/local/trace_*.json`.
- 33.2 trace integrity: PASS — request_id preserved end-to-end (test);
  deterministic trace_id `sha256(run|request|index)[:16]` (test);
  secrets redacted via reused `redact()` (test); CLI debugging via
  `scripts/trace_request.py --request <id>` (executed 4×).

## Section 34 — Reliability: all PASS

Failure matrix (`llm_adapter.FAILURE_MATRIX`, code-authoritative):

| Failure | Observed behavior |
|---|---|
| Timeout | 3 attempts (1+2), backoff [0.5,1.0,2.0], fallback `retry-exhausted:transient:TimeoutError` |
| API 5xx | 2 attempts, fallback `...:ProviderError` |
| 429 | 4 attempts, backoff [0.5,1.0,2.0,4.0], no storm |
| Invalid JSON | `None`, no retry, dropped |
| Unexpected output | strict gate rejects enum/type/null/extra-field |
| Missing evidence | UNKNOWN marker (conf 0), validator green |
| Image failure | `file_exists False` → UNKNOWN, never 0 |

- 34.2 fallback: PASS — explicit per-failure fallbacks; safe (no invented
  amount/date/plan); deterministic; logged (`rtrace.failures` + Trace).
  Pipeline fallback proven by injected `KeyError: home_currency` trace.
- 34.3 retry: PASS — attempts always exactly 1+max_retries; retryable =
  {Timeout, Connection, 429, 5xx}; non-retryable = {ValueError, TypeError,
  KeyError, JSONDecodeError}; backoff `min(8, 0.5·2ⁿ)` capped.

## Section 35 — Performance: all PASS (LOCAL MEASUREMENT)

Full dataset (250 req / 25342 events / 215 msgs / 16 imgs):

```text
TOTAL: 2.389s
data_load:                0.339s (14.2%)
join_canonicalization:    0.032s ( 1.4%)
evidence+forecast+decide: 2.016s (84.4%)  <- bottleneck, per-request avg 8.1ms
serialize:                0.001s
validate_consistency:     0.002s
```

- Bottleneck root cause: 90-day daily simulation per candidate
  (~110 simulates × 90 days per request) — inherent to the safety proof,
  not removable without weakening correctness. Per-request 8.1ms leaves
  large headroom; no optimization applied beyond indexing (correct call:
  35.1 says optimize bottlenecks, and this bottleneck IS the product).
- O(N²) fix: `build_contexts` message/image joins indexed by user/request;
  guard test asserts the per-request loop never scans full tables.
  Correctness proof: replay hash `d8386548…` byte-identical before/after.
- 35.2: 0 model calls / 0 tokens (E0); context minimization + selective
  gates unchanged and re-tested; images 16 total / 16 linked / 11 UNKNOWN;
  CACHE NOT ADOPTED (payloads unique; `_CACHE` empty after full run).
- 35.3 competition-time strategy: spec → deterministic core → validation →
  evaluation → evidence → reliability → observability → performance →
  polish; freeze architecture after core; submission buffer ≥30 min
  (this session finished with buffer; clean-room + replay in buffer).

## Final verification (commands + results)

- `pytest tests -q` → **354 passed** (30 new §§33–35 + 324 existing)
- `build_output.py` → 250 rows, mix 33/182/29/6, 2.6s
- `validate_output.py` → PASS
- replay_a == replay_b == output.csv (`d8386548…`) → IDENTICAL
- `clean_room_run.py` → CLEAN-ROOM PASS
- secret scan: `contains_secret` over src/scripts/output/usage_report → NONE;
  `git grep` hits are only redact patterns + synthetic test fixtures
- `git diff --check` → clean

## Traced requests (interview-ready)

1. `request_26` — affordable_now/full_payment; 4 candidates, 3×
   DEADLINE_EXCEEDED; earliest == request_date.
2. `request_28` — message_20 → amend_amount 1452 (deterministic); base
   breach → not_affordable; 1× UNSAFE + 2× DEADLINE.
3. `request_33` — blank event_3051 + image_06 → UNKNOWN (never 0);
   base breach → not_affordable.
4. `request_30` — affordable_with_plan/installments payment_option_83;
   9 candidates, 8 rejections (4× METHOD_NOT_ACCEPTED, 2× OUTRANKED,
   1× UNSAFE_MIN_BALANCE worst-day 2026-07-03, 1× DEADLINE_EXCEEDED).
5. Fallback injection (request_28, no home_currency) → `KeyError`
   → fallback row logged with `trace.status == fallback`.
   (`evaluation/local/trace_*.json`)

## Remaining gaps (outside §§33–35, §28 check)

- REMAINING GAP — Section: Winning §36 (docs) / build Module 34
  (interview). Item: interview-notes worked examples for new trace CLI.
  Why: new debugging path should be referenced. Evidence: this report.
  Recommended: 10-min edit post-deadline-buffer. Blocking? NO.
- REMAINING GAP — Section: packaging. Item: code.zip rebuilt by
  concurrent session (123 entries) BEFORE this report/checklist edits;
  final resync needs one rebuild + re-verify. Blocking? YES for
  submission — rebuild after final commit, re-run clean-room.
- No gaps found in security (§31), token accounting (§32), evaluation,
  architecture, or transcript logging from §§33–35 work. No secrets
  added. No determinism drift (hash unchanged).

## Files changed (this session; committed via 2291594 + dcceb53)

- Added: `src/affordai/observability/request_trace.py`,
  `scripts/trace_request.py`, `scripts/benchmark.py`,
  `tests/regression/test_sections_33_35.py`,
  `docs/implementation/sections-33-35-report.md` (this file)
- Modified: `src/affordai/pipeline.py` (indexed joins, RequestTrace
  wiring, rejection reasons), `src/affordai/evidence/llm_adapter.py`
  (429/5xx taxonomy, backoff, FAILURE_MATRIX),
  `src/affordai/evaluation/harness.py` (trace threading),
  Winning Checklist §§33–35 (marked below), `docs/build-checklist.md`
  Module 30 (measured evidence)

## Checklist update (§29 — evidence above)

33.1 [x] PASS · 33.2 [x] PASS · 34.1 [x] PASS · 34.2 [x] PASS ·
34.3 [x] PASS · 35.1 [x] PASS · 35.2 [x] PASS · 35.3 [x] PASS
