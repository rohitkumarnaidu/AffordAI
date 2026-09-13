# Model-Call Inventory (Sec 32.1 -- single source of truth)

> Every model call MUST have a contract. This file mirrors `src/affordai/evidence/llm_adapter.py:MODEL_CALLS`
> (code is authoritative). Any drift between this doc and `MODEL_CALLS` is a bug.

No provider SDK is vendored; both calls are gated behind `LLM_ENABLED=1` +
valid `API_KEY` (auto-loaded from repo-root `.env` via `_try_load_dotenv`,
never overriding exported env, never logging values). Disabled config runs with
0 calls, 0 tokens, 0 cost. Enabled config without a vendored backend records
`no-backend` `ModelCallRecord`s (estimated input tokens, LOCAL MEASUREMENT) and
adds 0 facts — decisions stay byte-identical (metered FINAL run 2026-09-13:
77 calls / 7864 est. input tokens / cost UNKNOWN, replay hash unchanged).

## Calls

### 1) `message_extract`

- **call_id:** `message_extract`
- **Provider:** `MODEL_PROVIDER` (empty in E0)
- **Model:** `MODEL_NAME` (empty in E0)
- **Trigger:** per request with >=1 message AND `needs_llm_for_messages()` true (deterministic facts already cover the request -> skip)
- **Purpose:** semantic interpretation of message text into typed facts only
- **Input scope:** single request -- minimized message contexts (ids + <=500ch text each); never other requests/users/dataset. Enforced via `minimize_message_context()` + `check_batch_safe()` (one request/user per call).
- **Output schema:** `list of {kind, source_type, source_id, request_id, user_id, event_id?, message_id?, image_id?, raw_value, normalized_value, confidence}`; `kind` must be in the 8-value allowlist; `confidence` finite in [0,1]
- **Validation:** `_validate_proposal` strict gate (rejects invalid JSON, missing fields, unknown enums, wrong types, NaN/Infinity, out-of-range, malformed dates, unsupported currencies, unexpected fields) + `min_confidence` + `EvidenceRegistry` ownership checks
- **Retry:** bounded `max_retries = LLM_MAX_RETRIES` (default 1, total attempts = 1+max_retries); transient errors only (timeout/connection); invalid schema never retries; never infinite
- **Fallback:** empty proposals + `fallback_reason`; deterministic interpreter facts still apply; downstream flow unchanged
- **Token measurement:** `ModelCallRecord` per attempt (`estimate_tokens` = ceil(chars/4) LOCAL MEASUREMENT; `token_source=estimated`); provider-reported usage wins when a backend reports it (`token_source=provider`)

### 2) `image_amount_extract`

- **call_id:** `image_amount_extract`
- **Provider:** `MODEL_PROVIDER` (same)
- **Model:** `VISION_MODEL_NAME` (empty in E0, falls back to `MODEL_NAME`)
- **Trigger:** per blank-amount event with >=1 linked image file that exists AND `needs_llm_for_image()` true
- **Purpose:** read the numeric amount from the linked receipt image only
- **Input scope:** single event -- `minimize_image_context(event_id, image_ids)`; kind forced to `amount`
- **Output schema:** same but `kind` MUST be `amount` with finite positive `normalized_value`
- **Validation:** `_validate_proposal` + `kind==amount` gate + `parse_amount()>0` + `min_confidence` + registry ownership; non-amount kinds from image path are dropped (zero-trust)
- **Retry:** same bounded budget
- **Fallback:** UNKNOWN amount marker (`amount_unknown_evidence`, confidence 0, blank is never zero); plan must stay safe without it
- **Token measurement:** same `ModelCallRecord` accounting

## Why no LLM on deterministic work

`forecast.py`, `payment_plans.py`, `optimizer.py`, `spending_changes.py`,
`eligibility.py`, `rules.py`, `decision.py`, `invariants.py` contain zero
LLM/clock/random imports (asserted by `tests/regression/test_sections_15_21.py::test_no_llm_or_clock_in_deterministic_core`).
Financial arithmetic, date math, FX conversion, 90-day forecast, minimum-balance
safety, plan generation/validation, deadline/ranking/decision are deterministic and
re-validated regardless of model output. Model output can never override them.

## Token / cost discipline (Sec 32.2-32.3)

- **Deterministic shortcuts:** `needs_llm_*` guards skip calls when no semantic value remains.
- **Selective calls:** one bounded extraction call per request (grouped where safe), never per-message fan-out; never every image blindly.
- **Context minimization:** only the needed request's minimized contexts are sent; no other requests/users/dataset.
- **Safe batching:** `check_batch_safe` fails closed on cross-request/user batches (prevents leakage/attribution errors).
- **No caching in E0:** payloads are unique per request; `ModelCache` is versioned (provider/model/prompt/schema/payload hash) and opt-in only when measured wins exist (documented `N/A` if not justified).
- **Retry budget:** finite, transient-only, no retry storms, no unbounded token spend; exhaustion -> deterministic safe fallback.
- **Instrumentation:** every call records timestamp/request_id/provider/model/purpose/in/out/total tokens/success/retry/fallback/token_source (secret-safe, no prompts/keys).
- **Estimate vs exact:** local `estimate_tokens` is marked `estimated`; never represented as provider billing. Real backend usage wins when available.
- **Pricing:** `src/affordai/evaluation/usage.py:PRICING` -- separate from business logic; cost is `UNKNOWN` when pricing unverified, never fabricated.
- **Report:** `evaluation/usage_report.md` (generated from `UsageReport.to_markdown()` for the FINAL full-dataset run) contains provider/model/calls/in/out/total/avg per request/total cost/per-request/per-model breakdown.

## Evidence that AI cannot override safety

- Typed facts only -> `EvidenceRegistry` -> `conflict_resolver` (cancel > settle > amend, newer same-source, settled > estimate, safer) -> `simulate()` floor gate -> `validator` re-derivation. Instruction-like text in messages/images has no mapped fact kind; even a proposed `amend_amount` is ownership-checked, then re-simulated.
