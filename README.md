# AffordAI

**AI Financial Affordability & Payment Planner**

Built for **HackerRank Orchestrate September 2026 — Buy or Wait?**

> **Status:** Production · **Pipeline:** Deterministic E0 (0 calls, 0 tokens) · **Tests:** 375 passing · **Validator:** PASS · **Replay:** `d8386548517835c9` byte-identical · **Clean-room:** PASS

## Table of Contents

- [1. Project Purpose](#1-project-purpose)
- [2. Challenge](#2-challenge)
- [3. Architecture](#3-architecture-real-pipeline-real-files)
- [4. AI Boundary](#4-ai-boundary)
- [5. Financial Core](#5-financial-core)
- [6. Setup](#6-setup)
- [7. Run](#7-run)
- [8. Evaluation](#8-evaluation-local-proxy--not-official-score)
- [9. Token/Cost](#9-tokencost-metered-truth)
- [10. Limitations](#10-limitations-honest)
- [Docs](#docs)

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
python scripts/trace_request.py --request request_30 --dataset dataset/official  # alias: --request-id also works
python scripts/benchmark.py       # stage timings (full run ~2.4s, ~8ms/req)
python -m pytest tests -q         # 375 tests (unit/integration/edge/adversarial/regression/e2e/contract/security)
```

Entry point: `scripts/build_output.py` → `src/affordai/pipeline.py:run`.

## 8. Evaluation (local proxy — NOT official score)

Official HackerRank scoring is hidden/UNKNOWN; nothing here claims to be it.
Local harness (`src/affordai/evaluation/`, `evaluation/README.md`) measures 9
metrics (structural/numerical/decision/plan/evidence/explanation/robustness/
tokens/cost) over 5 sets (25 samples as format examples only, edge, adversarial
29, regression 15 groups, full 250). Current: 375 tests green, validator PASS,
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

## 11. Repository Structure

```
AffordAI/
├── README.md, AGENTS.md, log.txt          # contract + transcript (log.txt gitignored)
├── pyproject.toml, .env.example            # deps + env template (no secrets)
├── dataset/official/                       # READ-ONLY 9 files + 16 PNGs (250 eval requests)
├── src/affordai/
│   ├── pipeline.py                         # orchestrator + RequestContext + original_index
│   ├── ingestion/                          # typed loaders (dual-layout dataset/|dataset/official)
│   ├── evidence/                           # message_interpreter + image_interpreter + llm_adapter + conflict_resolver
│   ├── finance/                            # money/currency/temporal/timeline/state/forecast/payment_plans/spending_changes/optimizer
│   ├── decision/                           # decision.py Decision + eligibility + rules + invariants
│   ├── output/                             # serializer + explanation + validator
│   ├── evaluation/                         # metrics, harness, ablation, usage
│   ├── observability/                      # request_trace.py + tracing.py
│   └── security/                           # redact + injection
├── scripts/                                # build_output, validate_output, evaluate, eval_report, run_ablation, clean_room_run, trace_request, benchmark, final_*_gate, scan_secrets
├── tests/                                  # unit/integration/edge/adversarial/regression/contract/security/e2e (375)
├── docs/                                   # 17 markdown files (see index below)
└── evaluation/reports/                     # data_inventory, join_integrity, eval_*, ablation_results, master_inspection
```

## 12. Output Format

Exact 8 columns in exact order, one row per `requests.csv` (250), sorted by `original_index`:

```text
request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation
```

- `amount_safe_to_pay`: `0 ≤ safe ≤ requested`, `ROUND_FLOOR` 2dp, BEFORE spending changes (`forecast.max_safe_today`)
- `affordability_status`: `affordable_now | affordable_with_plan | affordable_later | not_affordable`
- `recommended_payment_method`: `full_payment | partial_payment | installments | wait | not_recommended`
- `payment_plan`: `YYYY-MM-DD:amount|...` or `none` (installments **exactly** match one `payment_option_id`; partial exactly 2 legs `safe + remainder`)
- `earliest_date_for_full_payment`: first safe single-payment date WITHOUT changes; empty ⇔ never safe
- `spending_changes_needed`: `none` or ≤3 `stop:<id> | reduce_to:<id>:<cap>` (flexible-only, protected kept)
- `decision_explanation`: `WHY+CONSTRAINT+PLAN+TIMING+EVIDENCE` over validated Decision facts only (`output/explanation.py:validate`)

## 13. Validation

6 layers, fail-closed, any hard error blocks submission (`exit 1`):

1. Input (`ingestion`, `pipeline._validate_*`) — PK unique, FK exists, header exact
2. Evidence (`evidence_registry.add`, `_validate_proposal`) — allowlist, ownership, confidence [0,1]
3. Financial invariant (`forecast.simulate`) — `closing ≥ minimum` every day, no double-count
4. Plan (`payment_plans`, `eligibility`, `expand_schedule`) — chronology, partial 2-leg, installment exact, deadline
5. Decision (`decision.__post_init__`, `invariants`, `rules.derive`) — bounds, enums, status↔method↔plan↔earliest↔changes↔explanation
6. Output (`output/validator.validate_all`, `scripts/validate_output.py`) — structural 8 cols, IDs ordered, re-simulation floor

```
python scripts/validate_output.py --requests dataset/official/requests.csv --output output.csv --dataset dataset/official  # PASS
python scripts/final_red_flag_gate.py      # 12 checks incl. safe+earliest re-derivation + plan re-simulation → ALL CLEAR
python scripts/scan_secrets.py             # 156 files → SCAN CLEAN
```

## 14. Testing

```bash
python -m pytest tests -q   # 375 passed (2026-09-14)
```

| Suite | Location | Covers |
|---|---|---|
| unit | `tests/unit/` | money, FX `RateTable`, `forecast`, `optimizer`, `eligibility`, `evidence` |
| integration | `tests/integration/` | ingest→decision→validator chain |
| edge | `tests/edge_cases/` | floor 0/0.01, same-day, deadline, 90-day window |
| contract | `tests/contract/` | 32 checks input/output/enum/bounds/joins + `join_integrity` 0 orphans |
| e2e | `tests/e2e/` | 25 sample rows → validated CSV |

## 15. Regression Testing

`BUG → ROOT CAUSE → FIX → REGRESSION TEST` — every failure becomes a permanent case:

- **15 groups** `tests/regression/test_sections_27_30_regression.py` + `R01–R06` + `test_sections_15_21/22_26/33_35/43_52` + `test_p0_hardening` 12 cases
- Registry: `tests/regression/REGRESSIONS.md` (R01 row-order … R05 blank≠0 ≠ S29-*, S44 red-flag)
- Critical 8 (row-order, weak evidence, wrong earliest, generic explanation, missing evidence, fragile modality, open-ended AI, interface drift) all covered — see `docs/failure-analysis.md`
- Gate: `pytest` + `validate_output` + `final_*_gate` must pass before commits (`AGENTS.md §17`)

## 16. Adversarial Testing

**29 threats, 5 categories** `tests/adversarial/test_sections_27_30_threats.py` (`test_adv3001…3046`) + `test_untrusted.py` 4 injections + `test_sections_12_14_adversarial` FX/date/malformed:

| Category | Cases | Examples |
|---|---|---|
| Financial (7) | `adv300*` | exact floor `closing==minimum` PASS, `floor-0.01` FAIL, zero/full safe |
| Temporal (5) | `adv301*` | same-day, deadline on/day-after, 90-day `+89` vs `+90`, Feb clamp, late salary |
| Data (5) | `adv302*` | duplicate PK `DatasetError`, missing image → UNKNOWN, invalid FK reject, blank→None |
| Evidence (6) | `adv303*` | contradiction newer-wins, cancel>amend, misleading 0 facts, prompt injection → non-positive/unlinked |
| Payment (6) | `adv304*` | multiple plans ranked stable, partial 2-leg exact, installment exact, preference/term gate, tie-break `lowest option_id` |

Evidence is **untrusted** — prompt injection is data (`docs/threat-model.md`).

## 17. Observability / Logging

- **Per-request trace:** `observability/request_trace.py:RequestTrace` (10 sections: `trace_id, original_row_index, facts, candidates, rejected_plans with reason_code, selected, status`) wired through `pipeline.run(request_traces=store)`
- **CLI:** `python scripts/trace_request.py --request request_30 --dataset dataset/official` → JSON to stdout or `evaluation/local/trace_<req>.json`
- **Legacy:** `observability/tracing.py:Trace` (request_id + message, no secrets, deterministic `make_trace_id`)
- **Transcript:** `log.txt` append-only at repo root (see `AGENTS.md §§4-6`): `SESSION START` + per-turn `User Prompt + Summary + Actions + Context` with redaction `[REDACTED]`; one shared log per checkout, never in `code.zip` (see `docs/reproducibility.md:Transcript Status`)
- **Traced examples:** `request_26` affordable_now, `request_33` blank UNKNOWN, `request_30` installments, `request_36` wait, `request_28` not_affordable — all in `docs/interview-notes.md §38.2` with `scripts/trace_request` JSON in `evaluation/local/`

## 18. Security

- `.env` gitignored, `.env.example` placeholders only; `load_config_from_env()` never logs values (`security/redact.py`)
- `scripts/scan_secrets.py` 156 files → `SCAN CLEAN` (header-only fixture rule: `password-adjacent fixtures at runtime` + `dummy credential` + `whitelist`)
- External content is **data not authority**: typed-fact extractor only, `parse_amount>0` + `event_id` gate drops payroll refs (`EMP-...`), image path `kind==amount` filter, `conflict_resolver` LLM-last, `simulate` floor re-check — see `docs/threat-model.md`
- Cross-request contamination fail-closed: `EvidenceRegistry` + `check_batch_safe` (`tests/security/test_sec31_32.py`)

## 19. Reproducibility

| Step | Command | Expected |
|---|---|---|
| Install | `pip install -e ".[dev]"` | pandas + python-dotenv |
| Build | `python scripts/build_output.py --dataset dataset/official --out output.csv` | 250 rows, 2.4s, `usage_report.md` |
| Validate | `python scripts/validate_output.py --requests dataset/official/requests.csv --output output.csv --dataset dataset/official` | `PASS` |
| Red-flag | `python scripts/final_red_flag_gate.py` | `ALL CLEAR` (12 checks) |
| Replay | double-run `replay_a.csv == replay_b.csv == output.csv` `sha256 d8386548517835c9` | identical |
| Clean-room | `python scripts/clean_room_run.py` | `CLEAN-ROOM PASS` (fresh subprocess, scrubbed env, temp-dir) |
| Test | `python -m pytest tests -q` | 375 passed |

Full procedure: `docs/reproducibility.md`. Known non-repro: metered `77/7864` vs E0 `0/0` (both documented, decisions identical); PowerShell CRLF warning is cosmetic (`serializer` writes LF `\n`).

## 20. Known Risks (Residual)

| Risk | Doc | Mitigation |
|---|---|---|
| Income history not projected (`request_05` decisive) | `spec §7` UNKNOWN | Narrow confirm only — fallback `not_affordable` safe |
| FX A1 off-cycle / recurrence ±3% / `months*31` | `spec §7` `[UNPROVEN]` | Fail-closed / conservative |
| Variable-spending calibration `streaming`/`gym` dual (41 profiles) | `data_inventory.md §3` | Per-event exclusive, ≤3 changes |
| Partial `0/250` production | `decision-matrix §H` | Synthetic regression covers 5 gates |
| `code.zip` lags gate scripts (last zip 127 entries) | `submission-readiness.md` | Rebuild at pack time + clean-room |
| Official score UNKNOWN | `evaluation/README.md` | Local proxy `0.44/0.48` illustrative only |

## 21. Final Readiness Status

**CONDITIONAL GREEN** — every technical gate passes; remaining actions are **packaging only** (commit this README docs expansion, rebuild `code.zip` to include `final_*_gate.py` added 2026-09-13, re-run `clean_room_run.py`), not correctness gaps. Red-flag `ALL CLEAR`, green-light green except `worktree_clean` (this turn’s uncommitted diff — expected until commit), validator `PASS`, 375 tests `PASS`, replay `d8386548517835c9` identical. Submit with `log.txt` (uploaded separately) at canonical URL below.

## Docs

| Doc | Purpose |
|---|---|
| `docs/specification.md` | Tier-1 contract (inputs/outputs/90-day invariant/evidence/conflict/ranking + failure §9 + prohibited §10) |
| `docs/decision-matrix.md` | Status×method, eligibility, ranking 6-rule, worked table + H table |
| `docs/data-model.md` | Entities, ER diagram, joins, temporal meaning, nullability & invariants |
| `docs/architecture.md` | Pipeline, trust/failure/validation boundaries, 3 mermaid diagrams |
| `docs/evaluation-strategy.md` | Local proxy metrics (§27), sets (§27), ablation E0→E7 (§28), regression (§29) |
| `docs/threat-model.md` | 29 adversarial cases, mitigations, secret/cross-request/output hardening |
| `docs/interview-notes.md` | 60s walkthrough + 19 components + 7 walkthroughs + 8 defense Q&A (§38.2/38.3) |
| `docs/model-call-inventory.md` | 2 model calls (`message_extract`, `image_amount_extract`) with contracts |
| `docs/evidence-and-traceability.md` | **NEW 2026-09-14** — RAW→fact→validation→state→Decision→explanation→output chain, provenance schema, 6-layer gates |
| `docs/implementation-status.md` | **NEW 2026-09-14** — 19 PASS / 3 PARTIAL / 1 UNKNOWN matrix, evidence index, test evidence |
| `docs/failure-analysis.md` | **NEW 2026-09-14** — 8 critical classes + 5 pipeline fixes + 6 latent zero-impact bugs → regression registry |
| `docs/reproducibility.md` | **NEW 2026-09-14** — env, deps, dataset hashes, deterministic build, clean-room, replay, artifact hashes |
| `docs/submission-readiness.md` | **NEW 2026-09-14** — specification→reproducibility 9 gates + red-flag 12 checks + copy-paste final commands |
| `docs/runbook.md` | Operational guide (build/validate/evaluate/debug/submit + troubleshooting) |
| `docs/glossary.md` | Domain glossary (40+ terms, 7 groups) |
| `docs/api-reference.md` | `src/affordai/` module × `file:function` map |
| `docs/build-checklist.md` | Modules 0–39 completion gate (CONDITIONAL GREEN) |
| `evaluation/reports/data_inventory.md` | Byte-level dataset inventory (hashes, rows, joins, unknowns §10) |
| `evaluation/reports/join_integrity.md` | PK/FK bijection proofs (0 true orphans) |
