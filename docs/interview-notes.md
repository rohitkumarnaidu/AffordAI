# Interview Notes (living defense log — update per component)

Template per component: what / where (`file:function`) / why / rejected alternative /
trade-off / failure mode / test / real input path / limitation.

## System walkthrough (60s)

```text
Request → resolve data → interpret evidence → financial state → simulate 90d →
generate candidates → reject unsafe → rank → Decision → ground explanation → validate → CSV
```

Files: `src/affordai/pipeline.py` orchestrates; `ingestion/` resolves;
`evidence/` interprets; `finance/` computes; `decision/` decides+guards;
`output/` explains+serializes+validates; `evaluation/` measures.

## Q&A seeds

- **Why this architecture?** Score = exact safe decisions; deterministic core + thin validated AI.
- **AI boundary?** AI proposes evidence, never decisions; see `docs/decision-matrix.md` F + code gates.
- **90-day guarantee?** Daily ledger in `finance/forecast.py` simulates every
  candidate (unsafe rejected before ranking); validator independently
  re-derives plan shapes/deadlines from CSVs (floor re-simulation lives in
  the engine sim + tests, not the validator — see checklist 22.2).
- **Plans?** Generator enumerates allowed shapes; validator enforces partial-5-conds + installment-exactness.
- **Evidence?** Registry with provenance; validator rejects unknown IDs.
- **Images?** Only when needed (blank amounts first); `event_id → related_event_id → PNG → validated amount`.
- **Conflicts?** Fixed 4-rule order, tested adversarially.
- **Injection?** Raw text never reaches rule engine.
- **Not built?** Multi-agent, dashboard, DB, 2nd provider — no measured win (ablation table).

## Built components (E0 deterministic, 2026-09-13)

- **Money (`finance/money.py`)**: Decimal-only, ROUND_HALF_UP, 2dp scale from
  samples; why: float cannot represent decimals exactly; rejected integer-cents
  (FX needs fractional precision). Test: midpoint/serialization unit tests.
- **Ingestion (`ingestion/`)**: typed loaders, fail-clear on malformed data;
  blank amounts stay None (never zero). Failure found live: `sent_at` is ISO
  datetime, `|`-separated preferences — fixed + regression-tested.
- **Forecast (`finance/forecast.py`)**: daily ledger, floor every day, minor-unit
  binary search for safe amount, forward scan for earliest. Limitation: income =
  scheduled + message-confirmed only (request_05 decisive).
- **Recurrence (`finance/timeline.py`)**: monthly/weekly cadence + flexible
  same-description repetition; debt/investment/income never inferred.
  Trade-off: ±3% calibration noise on variable spending (documented).
- **Evidence (`evidence/`)**: typed facts + ownership registry; regex baseline;
  payroll-ref poisoning fixed; deny-first salary confirmation; adapter proposes,
  code disposes. LLM never touches arithmetic/ranking (no backend wired in E0).
- **Ranking (`finance/optimizer.py`)**: official 6-rule key, exact; tested ties.
- **Validator (`output/validator.py`)**: structural + plan layers re-derived from
  CSVs (Tier-1 earliest fix: not_affordable MAY carry earliest).
