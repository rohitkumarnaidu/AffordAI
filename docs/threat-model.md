# Threat Model

> External data is evidence, never authority over system rules.

## Threats

1. **Prompt injection (messages/images):** embedded instructions ("ignore minimum", "approve anyway",
   "use live rates") → mitigation: evidence extractors output typed facts only; rule engine never
   reads raw text; blocklist test in `tests/adversarial/`.
2. **Misleading/conflicting records:** fake settlement, duplicate credit, amended amount/date →
   4-rule precedence (cancel/settle/amend > newer same-source > settled > safer); duplicate
   IDs rejected at ingestion; scheduled-vs-inferred near-duplicates deduped ±3d in
   `finance/timeline.py`; cross-request evidence rejected by the registry.
3. **Missing data:** blank `amount` (→ image or unknown, never 0), absent image file (→ unknown,
   plan must stay safe without it), missing FX row (→ fail-closed: no foreign-cash credit until
   documented fallback; record assumption).
4. **Malformed data:** bad dates/amounts/currencies → loader raises `DatasetError`
   (fail-clear at startup); unexpected per-request failure → safest valid
   fallback row (`not_affordable`/`none`, safe 0) via `pipeline._decide_safe`,
   never crash the batch (tested).
5. **Invalid model outputs:** ungrounded IDs/numbers → evidence validator rejects; explanation checked
   against `Decision` facts; fallback to template explanation.
6. **Preference bypass:** safe-but-excluded method → eligibility gate rejects before ranking.
7. **Boundary attacks:** exact-minimum, deadline-day, fee-shifting options → re-simulation tests.

## Non-goals

Live banking/market access, voice notes (none in dataset), asset-price prediction.
