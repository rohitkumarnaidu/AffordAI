# Evaluation Report -- final (LOCAL MEASUREMENT)

- timestamp: 2026-09-13T11:16:46.658210+00:00
- dataset: dataset/official (n=250, fallbacks=0)
- version: E7-production (all components, deterministic, LLM off)
- runtime: 2.96s
- OFFICIAL score: UNKNOWN -- OFFICIAL HackerRank score: UNKNOWN (no official formula published). Every metric below is a LOCAL PROXY / LOCAL MEASUREMENT unless tagged otherwise.

## Metrics (27.2)

- structural_validity: errors=0 pass=True
- numerical_correctness: bounds_violations=[] pass=True
- plan_correctness: errors=0 pass=True
- evidence_validity: errors=0 pass=True
- explanation_consistency: rate=1.000 invalid=[]
- decision_consistency: errors=0 pass=True
- tokens: calls=0 total=0 (deterministic E0 (llm: LLM_ENABLED != 1))

## Failure categories (27.4)

- structural: 0
- identity: 0
- numeric: 0
- date: 0
- decision: 0
- payment: 0
- evidence: 0
- explanation: 0
- adversarial: 0
- regression: 0
- runtime: 0
- token_cost: 0

## Deltas vs baseline (2026-09-13T11:16:43.416588+00:00)

- structural_errors delta: 0
- plan_errors delta: 0
- evidence_errors delta: 0
- explanation_invalid delta: 0
- negative = fewer errors (improvement); positive = regression, reported honestly, never hidden

## Remaining failures

None -- all validator layers green on the full dataset.
