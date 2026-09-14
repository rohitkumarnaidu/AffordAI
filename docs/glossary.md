# Glossary — AffordAI Domain Terms

> **Version:** 1.0 · **Last updated:** 2026-09-14 · **Source:** `docs/specification.md` + `docs/data-model.md` (Tier-1 contract) + `evaluation/reports/data_inventory.md` (measured data)

## Table of Contents

- [Core Decision Terms](#core-decision-terms)
- [Financial Terms](#financial-terms)
- [Temporal Terms](#temporal-terms)
- [Evidence Terms](#evidence-terms)
- [Plan & Ranking Terms](#plan--ranking-terms)
- [Data & Integrity Terms](#data--integrity-terms)
- [Evaluation Terms](#evaluation-terms)

## Core Decision Terms

| Term | Definition | Output Field | Values |
|---|---|---|---|
| **Request** | One row in `requests.csv` (250 eval + 25 sample) asking for a purchase/travel/education/etc. commitment | `request_id` | `request_26 … request_275` |
| **Affordability Status** | Whether the request can complete safely within the 90-day forecast | `affordability_status` | `affordable_now \| affordable_with_plan \| affordable_later \| not_affordable` |
| **Recommended Payment Method** | The single method to use for this request | `recommended_payment_method` | `full_payment \| partial_payment \| installments \| wait \| not_recommended` |
| **Amount Safe to Pay** | Max safe to pay on `request_date` BEFORE optional spending changes; `0 ≤ safe ≤ requested`, `ROUND_FLOOR` 2dp | `amount_safe_to_pay` | Decimal, home currency |
| **Earliest Date for Full Payment** | First date full amount passes `closing ≥ minimum` as a single payment WITHOUT changes; empty ⇔ never safe | `earliest_date_for_full_payment` | `YYYY-MM-DD` or empty |
| **Payment Plan** | Chronological `YYYY-MM-DD:amount` legs joined by `\|` or `none` | `payment_plan` | `2025-08-03:15656000` etc. |
| **Spending Changes Needed** | `≤3` flexible-only changes `stop:<event_id> \| reduce_to:<event_id>:<amount>` or `none` | `spending_changes_needed` | `none` or `\|`-joined |
| **Decision Explanation** | Short grounded sentence over validated Decision facts only | `decision_explanation` | Template `WHY+CONSTRAINT+PLAN+TIMING+EVIDENCE` |

Status↔Method mapping: `affordable_now→full_payment`, `affordable_with_plan→partial/installments/full(with changes)`, `affordable_later→wait`, `not_affordable→not_recommended` (`docs/decision-matrix.md §A`).

## Financial Terms

| Term | Definition | Code |
|---|---|---|
| **Opening Balance** | `current_available_balance` in home currency at `request_date` | `finance/state.py:build` |
| **Minimum Balance to Keep** | Floor `closing_balance ≥ minimum` must hold every projected day | `finance/forecast.py:simulate` |
| **Home Currency** | User's `home_currency` (`INR\|ZAR\|IDR\|USD\|EUR`) — all money I/O in this currency | `financial_profiles.home_currency` |
| **Foreign Conversion** | Foreign cash → home via dated `RateTable` per **A1**: latest row on/before settlement for exact directed pair | `finance/currency.py:RateTable` |
| **Pending Debit** | `status=pending` + `direction=debit` — **reserved** at request_date | `timeline.build_flows` |
| **Pending Credit** | `status=pending` + `direction=credit` (+ bonuses/refunds/lottery) — **ignored** until settled | `timeline.build_flows` |
| **Scheduled / Settled** | Future confirmed flows — counted on `settlement_date` | `timeline.build_flows` |
| **Failed / Cancelled / Unrealized** | Excluded from forecast (no cash) | `timeline.build_flows` |
| **Recurrence** | Monthly (27–32d) or weekly (6–8d) with ≥4 occurrences; flexible same-description fallback ≥2, gap ≥7d | `timeline.py` |

Investments = affordability of *contributions* only (no price prediction, no advice).

## Temporal Terms

| Term | Definition | Code |
|---|---|---|
| **Request Date** | Day-0 of 90-day forecast window | `requests.request_date` |
| **Desired Completion Date** | Inclusive deadline — plan must complete `≤` this date | `requests.desired_completion_date`, `meets_deadline` |
| **Forecast End** | `request_date + 89` inclusive (90 days) | `finance/temporal.py:WINDOW_DAYS=90, forecast_end` |
| **Settlement Date** | Cash-movement date (forecast uses this; `event_date` is fallback for 10 unrealized rows) | `financial_events.settlement_date` |
| **Sent At** | `YYYY-MM-DDTHH:MM:SSZ` — orders message precedence | `messages.sent_at`, `conflict_resolver` |

## Evidence Terms

| Term | Definition | Code |
|---|---|---|
| **Evidence** | Typed fact with provenance `source_type/source_id/request_id/user_id/event_id/message_id/image_id/raw/normalized/confidence/method/sent_at` | `evidence/evidence_registry.py:Evidence` |
| **Provenance** | Full lineage of a fact; unsupported evidence never enters decisions | `evidence_registry.py:provenance()` |
| **Message Interpretation** | Regex `interpret(message)` emits typed facts `cancel/settle/confirm/delay/amend_amount/amend_date/preference` — raw text never reaches finance | `evidence/message_interpreter.py` |
| **Image Resolution** | `event_id → images.csv:related_event_id → media/images/<image_id>.png` (file_exists check); 16↔16↔16 bijection | `evidence/image_interpreter.py:resolve_images_for_event` |
| **Blank Amount** | `financial_events.amount == ""` → `amount_unknown_evidence` (confidence 0, `unknown`) — **never 0** | `finance/money.py:parse_amount_safe` |
| **Conflict Precedence** | `explicit cancel/settle/amend > newer same-source > settled > safer` + deterministic-over-LLM + lexical tiebreak | `evidence/conflict_resolver.py:resolve` |
| **LLM Adapter** | Bounded `propose_facts` (allowlist, schema gate, `min_confidence`, validated-or-dropped, `no-backend` fallback) | `evidence/llm_adapter.py` |
| **Untrusted Evidence** | `messages.csv` text, PNG bytes, model output — never authority; prompt injection is data, not instructions | `docs/threat-model.md` |

## Plan & Ranking Terms

| Term | Definition | Code |
|---|---|---|
| **Full Payment** | `request_date:requested` single leg | `finance/payment_plans.py:generate` |
| **Partial Payment** | Exactly 2 legs `request_date:safe \| earliest:(requested−safe)` summing to requested; 5 strict gates | `payment_plans.generate` + `decision-matrix.md §B` |
| **Installments** | Must **exactly match** one `payment_option_id` schedule (dates+amounts+count+fees inclusive) | `payment_plans.expand_schedule` |
| **Wait** | Single future leg `earliest:requested` — requires future-safe full + user accepts `full_payment` | `payment_plans.generate` |
| **Not Recommended** | Fallback `none` when no safe eligible plan exists | `pipeline.py:decide_context` |
| **Spending Change** | `stop:<id>` or `reduce_to:<id>:<cap>` — flexible-only, protected kept, ≤3, stop/reduce exclusive per event | `finance/spending_changes.py` |
| **Ranking (6-rule)** | `deadline → no-changes → min total → earlier start → fewer payments → lowest option_id` | `finance/optimizer.py:rank_key` |

## Data & Integrity Terms

| Term | Definition | Code |
|---|---|---|
| **Original Index** | Input row order in `requests.csv` — preserved end-to-end, output sorted by it | `pipeline.RequestContext.original_index` |
| **RequestContext** | `original_index, request_id, user_id, request, profile, events, messages, images, options, evidence` | `pipeline.py:RequestContext` |
| **Decision** | Frozen canonical 8-field object — single source of truth, `0 ≤ safe ≤ requested` | `decision/decision.py:Decision` |
| **Join Integrity** | All PKs unique, all FKs resolve (0 true orphans; 71+12+5 superset artifacts for sample 01..25 are not orphans) | `evaluation/reports/join_integrity.md` |
| **Canonical Columns** | `OUTPUT_COLUMNS` exact order 8 cols — byte-identical between `decision.py` and `output.csv:1` | `decision/decision.py:OUTPUT_COLUMNS` |

## Evaluation Terms

| Term | Definition | Source |
|---|---|---|
| **OFFICIAL** | HackerRank hidden evaluation — always UNKNOWN unless Tier-1 proves otherwise | `evaluation/README.md` |
| **LOCAL MEASUREMENT** | Number this repo actually computed and can reproduce (e.g. validator PASS, replay hash) | `evaluation/README.md` |
| **LOCAL PROXY** | Locally reconstructed stand-in (e.g. 0.44/0.48 sample accuracy vs `sample_requests.csv` — illustrative only, NOT eval labels) | `evaluation/README.md` |
| **INFERENCE** | Conclusion drawn from evidence, labelled as such | `evaluation/README.md` |
| **UNKNOWN** | Cannot be verified from available sources | `evaluation/README.md` |
| **Ablation E0→E7** | `E0` deterministic baseline → `E1`+messages → `E2`+images → `E3` conflicts → `E4` optimizer → `E5` explanations → `E6` validation → `E7` token trim — keep only on measured win | `docs/evaluation-strategy.md §28` |
