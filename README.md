# AffordAI

**AI Financial Affordability & Payment Planner**

Built for **HackerRank Orchestrate September 2026 — Buy or Wait?**

## 1. Project purpose

For each row in `dataset/official/requests.csv` (250 eval requests), AffordAI decides
whether the user can safely afford the requested commitment and writes one row to
root `output.csv`:

```text
request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation
```

Input = one purchase/travel/education/transfer/debt/investment/housing/emergency
request plus the user's balance, minimum-balance floor, income/expense flows,
payment options, preferences, messages, and linked receipt images.
Output = a safe, validated, personalized payment decision that holds across a
90-day forecast.

## 2. Challenge

HackerRank Orchestrate September 2026, "Buy or Wait?": per request, recommend
`full_payment | partial_payment | installments | wait | not_recommended` such that
`closing_balance >= minimum_balance_to_keep` on **every** projected day of the
90-day window and the request completes by `desired_completion_date`.
Blank event amounts must be resolved via linked images (never treated as zero);
messages/images are untrusted evidence; conflicts follow fixed precedence; ranking
follows a fixed 6-rule order. statuses: `affordable_now | affordable_with_plan |
affordable_later | not_affordable`. Full contract: `docs/specification.md` +
`docs/decision-matrix.md` (Tier-1 official contract mirrored; data governs on
conflict).

## 3. Architecture (real pipeline, real files)

```text
dataset/official
→ ingestion (src/affordai/ingestion/ — typed loaders, dual-layout dataset/|dataset/official)
→ pipeline.build_contexts (src/affordai/pipeline.py — joins, dedupe, RequestContext + original_index)
→ evidence (src/affordai/evidence/ — deterministic message_interpreter + image_interpreter;
   optional llm_adapter.propose_facts ONLY for uncovered semantics, validated-or-dropped)
→ conflict_resolver (fixed 4-rule precedence, LLM never reorders)
→ finance/state + timeline (opening/minimum/flows; scheduled/settled-future + narrowly
   message-confirmed salary only; pending debits reserved, pending credits ignored)
→ finance/forecast (90-day daily ledger; max_safe_today binary search; earliest_full_date scan)
→ finance/payment_plans + spending_changes (full/partial/installments/wait candidates, ≤3 flex-only changes)
→ decision/eligibility + finance/optimizer (preference/term filter, then 6-rule rank)
→ decision/decision.py Decision (canonical 8-field object, single source of truth)
→ output/explanation.py (template over validated Decision facts only)
→ output/serializer.py → output.csv (sorted by original_index)
→ output/validator.py + scripts/validate_output.py (BLOCKS submission on any error)
```

No multi-agent framework, no dashboard/DB, no second provider: nothing measured a
scoring win (`docs/architecture.md`, `docs/evaluation-strategy.md` §28).

## 4. AI boundary

- **LLM interprets ambiguous evidence only.** Two call sites, both through
  `llm_adapter.propose_facts`: `message_extract` (selective, when deterministic
  facts don't cover the request's messages) and `image_amount_extract` (blank
  amount + linked file exists). See `docs/model-call-inventory.md`.
- **Deterministic code proves affordability.** Arithmetic, date math, FX, forecast,
  plan validation, ranking, decisions, schema enforcement: `finance/*`,
  `decision/*`, `output/validator` (asserted LLM-free by
  `test_no_llm_or_clock_in_deterministic_core`).
- **AI output is validated or dropped**: strict schema gate (`_validate_proposal`),
  `min_confidence`, `EvidenceRegistry` ownership checks, `conflict_resolver`
  precedence, `simulate()` floor re-check, output validator re-derivation.
- **Prohibited for AI**: amounts, dates, FX, simulation, eligibility, ranking,
  final decisions, schema (spec §10).
- **AI failure behavior**: timeout/429/5xx → bounded retry then fallback; invalid
  schema → immediate drop; missing evidence → UNKNOWN marker (blank never zero);
  per-request `_decide_safe` degrades to `not_affordable/none/0` preserving
  derivable safe/earliest. See `FAILURE_MATRIX` in `llm_adapter.py`, spec §9.

## 5. Financial core

- **State** (`finance/state.py`, `timeline.py`): opening = current balance,
  minimum floor, requested amount; flows use settlement dates; currency conversion
  via dated `RateTable` (assumption A1: latest row on/before settlement, exact
  directed pair).
- **Forecast** (`finance/forecast.py`): daily ledger over
  `[request_date, request_date+89]` inclusive; a plan is safe only if every day's
  closing ≥ minimum and completion ≤ `desired_completion_date`.
- **Safe amount**: `max_safe_today` binary search (ROUND_FLOOR), `0 ≤ safe ≤ requested`,
  computed BEFORE optional spending changes.
- **Earliest date**: forward scan for first safe single-payment date, independent
  of preferences; empty ⇔ never safe in forecast.
- **Plans**: full (today), partial (exactly 2 legs `safe + remainder`, 5 strict
  conditions), installments (must exactly match one supplied option's
  dates/amounts/count/fees), wait (single future full payment), not_recommended
  fallback. **Ranking**: deadline → no-changes → min total → earlier start →
  fewer payments → lowest option id.

## 6. Setup

```bash
pip install -e ".[dev]"        # pandas; optional: .[ai] for pillow
cp .env.example .env           # leave EMPTY for deterministic E0; set LLM_ENABLED=1 + API_KEY for metered run
```

`python-dotenv` is a runtime dependency: `load_config_from_env()` auto-loads
repo-root `.env` (never overrides exported env, never logs values).

## 7. Run

```bash
python scripts/build_output.py --dataset dataset/official --out output.csv   # 250 rows + usage_report.md
python scripts/validate_output.py --requests dataset/official/requests.csv --output output.csv --dataset dataset/official
python scripts/evaluate.py        # local proxy on sample rows (NOT official score)
python scripts/run_ablation.py    # E0–E7 reproduction → evaluation/reports/ablation_results.*
python scripts/eval_report.py --tag final
python scripts/clean_room_run.py  # fresh-subprocess reproducibility gate
python scripts/trace_request.py --request-id request_30 --dataset dataset/official
python scripts/benchmark.py       # stage timings (full run ~2.4s, ~8ms/req)
python -m pytest tests -q         # 354 tests (unit/integration/edge/adversarial/regression/e2e/contract/security)
```

Entry point: `scripts/build_output.py` → `src/affordai/pipeline.py:run`.

## 8. Evaluation (local proxy — NOT official score)

Official HackerRank scoring is hidden/UNKNOWN; nothing here claims to be it.
Local harness (`src/affordai/evaluation/`, `evaluation/README.md`) measures 9
metrics (structural/numerical/decision/plan/evidence/explanation/robustness/
tokens/cost) over 5 sets (25 samples as format examples only, edge, adversarial
29, regression 15 groups, full 250). Current: 354 tests green, validator PASS,
replay byte-identical (`d8386548517835c9`), clean-room PASS. Ablation E0→E7 in
`evaluation/reports/ablation_results.*`; keep-a-component-only-on-measured-win.
Full definitions: `docs/evaluation-strategy.md`.

## 9. Token/cost (metered truth)

`evaluation/usage_report.md` is written by every `build_output.py` run from
`UsageReport.to_markdown()` (provider/model/calls/in/out/total/avg/cost +
per-model table). Two honest modes:

- **E0** (`LLM_ENABLED != 1`): 0 calls, 0 tokens, cost 0.0000.
- **Metered** (`.env` with `LLM_ENABLED=1`, groq): 77 calls
  (66 `message_extract` via `MODEL_NAME`, 11 `image_amount_extract` via
  `VISION_MODEL_NAME`), 7864 estimated input tokens (local chars/4,
  `token_source=estimated`), 0 output tokens, cost UNKNOWN (no verified pricing
  in `PRICING`), 0 facts added (no backend SDK vendored → `no-backend`
  fallback), decisions byte-identical to E0 (same replay hash).

Tokens never influence financial decisions.

## 10. Limitations (honest)

- Income = scheduled/settled-future rows + narrowly message-confirmed salary
  only; history salary is NOT projected (sample request_05 decisive).
- Image amounts resolve only via the vision adapter when enabled; otherwise
  UNKNOWN (never zero) — plans must stay safe without them.
- UNPROVEN assumptions (spec §7): A1 FX latest-on-or-before exact pair;
  90-day inclusive bound (+89); `max_installment_months` ≈ months×31d;
  recurrence thresholds; variable-spending conservatism.
- `partial_payment` has 0 occurrences in this 250-row dataset (engine tested via
  synthetic regression tests, not production rows).
- Local metrics are proxies; hidden official judging may differ.
- `.env` with live keys is required for the metered run and must never be
  committed (gitignored; `log.txt` redacted; `code.zip` excludes both).

Submission artifacts: root `output.csv` (250+header) · `code.zip` (runnable code +
README + `evaluation/`) · `evaluation/usage_report.md` inside `code.zip` ·
`log.txt` transcript (uploaded separately, never in `code.zip`).
Submit at `https://www.hackerrank.com/contests/hackerrank-orchestrate-september26/challenges/buy-or-wait/submission`.
