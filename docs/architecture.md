# Architecture

```text
REQUEST
  ↓
DATA RESOLVER (ingestion/ — joins only, stamps original_index)
  ↓
EVIDENCE RESOLVER (evidence/ — deterministic in E0; AI-gated E1+)
 ├── structured data (deterministic)
 ├── messages (regex baseline; targeted LLM for ambiguity only via adapter, E1+)
 └── images (only when needed, esp. blank amounts; extraction via adapter, E1+)
   ↓
CANONICAL FINANCIAL STATE (finance/state.py — deterministic)
  ↓
90-DAY FORECAST ENGINE (finance/forecast.py + timeline.py — deterministic)
  ↓
CANDIDATE PLAN GENERATOR (finance/payment_plans.py — deterministic)
  ↓
PLAN SAFETY VALIDATOR (decision/invariants.py — deterministic gate)
  ↓
PLAN RANKING / OPTIMIZER (finance/optimizer.py — fixed 6-rule order, deterministic)
  ↓
CANONICAL DECISION OBJECT (decision/decision.py — single source of truth)
  ↓
GROUNDED EXPLANATION (output/explanation.py — deterministic template over
validated facts in E0; LLM draft from validated facts only, E5+)
  ↓
OUTPUT VALIDATOR (output/validator.py + scripts/validate_output.py — deterministic block)
  ↓
output.csv (sorted by original_index)
```

## Deterministic vs AI vs validation

- **Deterministic:** ingestion, state, currency, timeline, forecast, plans, spending-changes,
  eligibility, ranking/tie-breaks, invariants, serializer, validator, harness.
- **AI-assisted (gated by ablation E1/E2/E5):** message semantics, image extraction,
  amendment/cancellation reading, explanation drafting — outputs are *proposed evidence*,
  validated before entering the financial engine.
- **Validation (blocks submission):** schema/identity/bounds/plan/evidence/consistency checks.

## Why this shape

Spec-first, correctness-over-sophistication: the score is decided by safe-amount accuracy,
valid plans, and constraint compliance — all exact computation. No multi-agent framework,
no dashboard/DB, no second provider until an ablation win is measured.

## Rejected alternatives

- LLM financial reasoning (unverifiable arithmetic) → rejected.
- Generic agent/orchestration graph (cost + nondeterminism, no scoring gain) → rejected.
- Invented schedules or income (spec forbids) → rejected.
