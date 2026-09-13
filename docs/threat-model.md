# Threat Model -- Adversarial / Hidden-Test Resistance (Sections 30, 32, 34)

> External data is evidence, never authority over system rules. The deterministic
> financial contract, 90-day safety invariant, minimum-balance floor, payment
> rules, and ranking rules are authoritative. Prompt injection is data, not instructions.

## Contract

All messages/images are UNTRUSTED EVIDENCE. They must NEVER override: system contract,
official challenge rules, deterministic financial constraints, minimum-balance safety,
payment rules (partial 5-conds, installment exactness), ranking rules. Provenance is
preserved per src/affordai/evidence/evidence_registry.py; unsupported evidence never
enters decisions.

## 30.1 Financial adversarial (7) -- tests/adversarial/test_sections_27_30_threats.py::test_adv300*

1. exact minimum-balance boundary -- closing == minimum passes
2. just-below boundary -- closing 0.01 under fails
3. just-above boundary -- closing 0.02 above passes
4. zero safe amount -- safe 0, earliest None, zero-payment simulates ok
5. full requested amount safe -- safe == requested, earliest == request_date
6. future income timing -- income one day before earliest fails, on-day passes
7. large essential expense -- blocks full window, safe 0

Verified: expected balance, expected affordability, amount_safe_to_pay, chosen plan, safety invariant (simulate).

## 30.2 Temporal adversarial (5) -- test_adv301*

1. same-day payment -- request_date payment safe when balance allows
2. deadline boundary -- on-deadline eligible, day-after dropped, ranking prefers on-time
3. 90-day boundary -- forecast_end = request_date+89, day 89 visible, day 90 invisible
4. recurrence boundary -- Feb clamp 28/29, monthly generator survives month-end
5. late salary -- salary one day before earliest fails, on-salary-day passes

Verified: date calculations independently re-derived (temporal.py single source).

## 30.3 Data adversarial (5) -- test_adv302*

1. duplicate event -- duplicate ids rejected (DatasetError), no double-count
2. missing event -- missing event_id resolves to empty image list, no crash
3. missing image -- missing file -> file_exists False, amount stays UNKNOWN (never 0)
4. invalid reference -- fake event/message ids rejected by EvidenceRegistry
5. blank amount -- blank -> None never 0; UNKNOWN marker ("unknown", confidence 0)

Verified: no crash, no fabricated amount, no invalid reference, no cross-request contamination, safe fallback.

## 30.4 Evidence adversarial (6) -- test_adv303*

1. contradictory message -- newer same-event fact wins (sent_at descending)
2. cancellation -- cancel beats amend (explicit precedence)
3. amendment -- uncontested amend applies via amended_amounts
4. misleading evidence -- irrelevant text yields 0 facts; payroll refs without salary keywords yield 0 amount facts
5. prompt injection -- embedded instructions ("ignore previous rules", "approve regardless of balance", "change amount", "treat image as authoritative") map to at most non-positive or unlinked amounts, dropped by parse_amount>0 + event_id gate; deterministic floor unmoved
6. malicious image text -- non-amount image facts have kind != amount and are dropped by pipeline kind filter; UNKNOWN marker used when no file

Verified: deterministic contract authoritative, provenance preserved, conflict rules applied, unsafe overrides rejected, fabricated evidence impossible, explanations grounded.

## 30.5 Payment adversarial (6) -- test_adv304*

1. multiple valid plans -- ranked deterministically, input-order proof (select stable)
2. partial allowed -- 2-payment shape sum == requested, safe/earliest gates satisfied
3. partial disallowed -- allows_partial=False yields 0 partial candidates
4. installment exact match -- option id/count/dates/amounts/fees matched via expand_schedule
5. installment rejected by preference -- installments dropped when profile excludes method or max_installment_months None
6. tie-break -- lowest option_id wins, order-proof

Verified: candidates generated correctly, invalid rejected, preferences/deadline/safety respected, ranking deterministic, tie-break deterministic, never invent schedule.

## Additional hardening (pre-existing suites)

- tests/adversarial/test_untrusted.py -- injection variants inert, malicious ref no amount, duplicate rejection, malformed amounts, cross-request rejection, confidence bounds
- tests/adversarial/test_sections_12_14_adversarial.py -- conflicting rates rejected, malformed dates raise, missing currencies rejected, negative/zero/huge amounts, temporal anomalies

## Mitigations summary

| Threat | Mitigation | Evidence |
|---|---|---|
| Prompt injection | Typed-fact extractor only; rule engine never reads raw text; pipeline drops non-positive/unlinked amounts; kind filter on image path | message_interpreter.py, evidence_registry.py, pipeline _collect_evidence |
| Misleading/conflicting | 4-rule precedence (cancel/settle/amend > newer > settled > safer), duplicate IDs rejected, cross-request rejected | conflict_resolver.py, ingestion, evidence_registry |
| Missing data | blank != 0 (UNKNOWN), missing image file -> UNKNOWN, missing FX -> fail-closed | image_interpreter, money.py, currency.py |
| Malformed | DatasetError at ingestion; per-request fallback safest valid row (not_affordable/none) | pipeline._decide_safe, ingestion |
| Invalid model outputs | Evidence validator rejects unknown ids; explanation validated against Decision; fallback template | evidence_registry, output/explanation.py |
| Preference bypass | Eligibility gate rejects before ranking | decision/eligibility.py |
| Boundary | Re-simulation tests at exact floor, deadline, 90-day, fee-shifting | finance/forecast, tests |

## Non-goals

Live banking/market access, voice notes (none in dataset), asset-price prediction.
