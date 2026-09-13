# AffordAI

**AI Financial Affordability & Payment Planner**

Built for **HackerRank Orchestrate September 2026 — Buy or Wait?**

## What it does

For each row in `dataset/official/requests.csv`, AffordAI decides whether the user can
safely afford the requested commitment and writes one row to `output.csv`:

```text
request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation
```

## Core idea

- Structured financial data + payment options + dated FX rates → deterministic financial truth.
- Messages/images → validated evidence (targeted AI only where semantics are ambiguous).
- 90-day forecast enforces `closing_balance >= minimum_balance_to_keep` on every day.
- Candidate plans (full / partial / installments / wait / not_recommended) are simulated,
  validated, then ranked by the official priority order.
- Grounded explanations cite only validated facts; the output validator blocks bad rows.

## Architectural principle

> AI interprets ambiguous evidence. Deterministic code computes financial truth.

See `docs/architecture.md` and `docs/specification.md`.

## Running

```bash
pip install -e ".[dev]"
python scripts/build_output.py --dataset dataset/official --out output.csv
python scripts/validate_output.py --requests dataset/official/requests.csv --output output.csv --dataset dataset/official
python scripts/evaluate.py  # local proxy on sample_requests.csv (NOT official score)
python scripts/clean_room_run.py  # fresh-env build + validate
```

Entry point: `scripts/build_output.py` (loads `dataset/official`, runs the
deterministic pipeline in `src/affordai/pipeline.py`, writes root `output.csv`).

## Evaluation / cost

Local proxy on the 25 sample rows (E0 deterministic, NOT official score):
status 0.44 / method 0.56 / earliest-exact 0.36. Samples are illustrative
format examples, not eval labels.
Token/cost accounting for the final full-dataset run lives in `evaluation/usage_report.md`
(250 rows, ~2.4s wall, 0 model calls, deterministic, byte-identical replay).

## Safety

- No secrets in git (`.env` ignored, `.env.example` committed).
- Official data never modified; messages/images treated as untrusted evidence.
- Known limitations: income is scheduled/settled-future plus narrowly
  message-confirmed salary only (no history-projected salary — see
  `docs/specification.md` assumptions); image amounts resolve only via the
  vision adapter when enabled, otherwise stay unknown (never zero);
  `docs/build-checklist.md` tracks the full gate.
