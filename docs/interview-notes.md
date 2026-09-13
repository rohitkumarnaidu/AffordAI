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
- **90-day guarantee?** Daily ledger in `finance/forecast.py`; invariant checker re-simulates every plan.
- **Plans?** Generator enumerates allowed shapes; validator enforces partial-5-conds + installment-exactness.
- **Evidence?** Registry with provenance; validator rejects unknown IDs.
- **Images?** Only when needed (blank amounts first); `event_id → related_event_id → PNG → validated amount`.
- **Conflicts?** Fixed 4-rule order, tested adversarially.
- **Injection?** Raw text never reaches rule engine.
- **Not built?** Multi-agent, dashboard, DB, 2nd provider — no measured win (ablation table).
