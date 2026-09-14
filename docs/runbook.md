# Runbook — AffordAI Operations

> **Version:** 1.0 · **Last updated:** 2026-09-14 · **Scope:** Build, validate, evaluate, debug, and submit AffordAI
> Companion to `README.md` §§6–7. Every command is copy-pasteable on Windows PowerShell 5.1 and POSIX.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start (E0 Deterministic)](#quick-start-e0-deterministic)
- [Metered Run (LLM Enabled)](#metered-run-llm-enabled)
- [Validation Gate](#validation-gate)
- [Evaluation & Ablation](#evaluation--ablation)
- [Debugging Single Requests](#debugging-single-requests)
- [Benchmark & Profiling](#benchmark--profiling)
- [Clean-Room Reproducibility](#clean-room-reproducibility)
- [Submission Packaging](#submission-packaging)
- [Troubleshooting](#troubleshooting)
- [Script Reference](#script-reference)

## Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Python | ≥3.11 | `python --version` |
| pandas | ≥2.0 | `pip show pandas` |
| python-dotenv | ≥1.0 | `pip show python-dotenv` |
| pytest | ≥8.0 (dev) | `pip show pytest` |
| Pillow | ≥10.0 (optional, for image vision) | `pip show pillow` |

```bash
pip install -e ".[dev]"        # deterministic E0 — all you need
pip install -e ".[dev,ai]"     # + vision support (Pillow)
cp .env.example .env           # leave EMPTY for E0; fill for metered run
```

`.env` is gitignored. Never commit it. `load_config_from_env()` auto-loads repo-root `.env` without overriding exported env vars and never logs values.

## Quick Start (E0 Deterministic)

E0 runs with **0 model calls, 0 tokens, 0 cost** — the shipped production path.

```powershell
# 1. Build output (250 rows)
python scripts/build_output.py --dataset dataset/official --out output.csv
# expected: 250 rows, ~2.4s, evaluation/usage_report.md written (0/0/0.0000)

# 2. Validate
python scripts/validate_output.py --requests dataset/official/requests.csv --output output.csv --dataset dataset/official
# expected: PASS (structural + plan)

# 3. Evaluate (local proxy — NOT official score)
python scripts/evaluate.py
# 4. Ablation E0→E7
python scripts/run_ablation.py

# 5. Test
python -m pytest tests -q
# expected: 375 passed
```

Entry point: `scripts/build_output.py` → `src/affordai/pipeline.py:run` → `output.csv` sorted by `original_index`.

## Metered Run (LLM Enabled)

Requires `.env` with `LLM_ENABLED=1` + provider keys (see `.env.example`). No SDK vendored — metered run records `no-backend` `ModelCallRecord`s (estimated tokens) and adds 0 facts; decisions stay byte-identical.

```powershell
# .env
LLM_ENABLED=1
MODEL_PROVIDER=groq
MODEL_NAME=qwen/qwen3.6-27b
VISION_MODEL_NAME=groq/compound
GROQ_API_KEY=[REDACTED]

python scripts/build_output.py --dataset dataset/official --out output.csv
cat evaluation/usage_report.md
# expected: 77 calls (66 message_extract + 11 image_amount_extract), 7864 est. tokens, cost UNKNOWN, replay hash unchanged
```

Token/cost discipline: selective calls (`needs_llm_*` guards), minimized contexts, `check_batch_safe`, `PRICING` separate from logic. See `docs/model-call-inventory.md`.

## Validation Gate

`output/validator.py` + `scripts/validate_output.py` is the **final submission gate** — any hard error blocks submission (exit 1). Six layers: structural → evidence → financial invariant → plan → decision → output.

```powershell
python scripts/validate_output.py --requests dataset/official/requests.csv --output output.csv --dataset dataset/official
python scripts/final_red_flag_gate.py    # 12 red-flag checks (row count, floor re-derivation, plan re-simulation)
python scripts/final_green_light_gate.py # green-light checklist
python scripts/scan_secrets.py           # secret scan (156 files, header-only fixtures whitelisted)
```

All gates must be **PASS / ALL CLEAR / SCAN CLEAN** before packaging `code.zip`.

## Evaluation & Ablation

| Script | Purpose | Output |
|---|---|---|
| `scripts/evaluate.py` | Local proxy on sample rows | console summary |
| `scripts/eval_report.py --tag final` | Full 250-row baseline/final reports | `evaluation/reports/eval_*.json/.md` |
| `scripts/run_ablation.py` | E0→E7 reproduction (23s) | `evaluation/reports/ablation_results.*` |

Metrics: 9 definitions in `src/affordai/evaluation/metrics.py:METRIC_DEFS` (structural, numerical, decision, plan, evidence, explanation, robustness, tokens, cost). Official score = UNKNOWN — never claim local = official (`evaluation/README.md`).

## Debugging Single Requests

```powershell
# Trace one request end-to-end (facts → state → forecast → candidates → decision)
python scripts/trace_request.py --request request_30 --dataset dataset/official
python scripts/trace_request.py --request-id request_26 --dataset dataset/official  # alias

# Outputs JSON with 10 trace sections: ids, facts, flows, safe/earliest, candidates, rejections, selection, decision
# Also writes evaluation/local/trace_<request>.json when --out not specified
```

Traced examples in `docs/interview-notes.md §38.2`: `request_26` (affordable_now), `request_33` (image UNKNOWN), `request_30` (installments), `request_36` (wait), `request_28` (not_affordable).

## Benchmark & Profiling

```powershell
python scripts/benchmark.py
# TOTAL: 2.389s
# data_load:             0.339s (14.2%)
# join_canonicalization: 0.032s (1.4%)
# evidence+forecast+decide: 2.016s (84.4%) — bottleneck is 90-day daily simulation (~110 sims × 90 days/req), inherent to safety proof
# serialize:             0.001s
```

Per-request avg **8.1ms**; headroom is large. Indexed joins (`by_user`, `by_request`) eliminate O(N²) scans — proven by `d8386548517835c9` replay-identical before/after.

## Clean-Room Reproducibility

Fresh subprocess, scrubbed env (no `KEY`/`TOKEN` in env), temp-dir output, no hidden state:

```powershell
python scripts/clean_room_run.py
# expected: CLEAN-ROOM PASS (250 rows, validator PASS, ~3s, byte-identical replay)
```

Scope: fresh **process** validation (stdlib-only runtime needs no install). Evaluator isolation beyond this is not claimed (`docs/build-checklist.md:31.1`).

## Submission Packaging

```powershell
# Rebuild after final commits (includes gate scripts added post-last-zip)
python -c "import zipfile, pathlib; print('code.zip entries:', len(zipfile.ZipFile('code.zip').namelist()))"
# Verify: no .env, no __pycache__, no log.txt, no secrets inside
python scripts/scan_secrets.py  # must be SCAN CLEAN

# Final artifacts (AGENTS.md §26):
# - output.csv (root, 250+header)
# - code.zip (runnable code + README + evaluation/ incl. usage_report.md)
# - log.txt (uploaded separately, never in code.zip)
# Submit: https://www.hackerrank.com/contests/hackerrank-orchestrate-september26/challenges/buy-or-wait/submission
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `DatasetError: duplicate PK` | CSV has duplicate ids | Check `dataset/official/*.csv` integrity; `python scripts/validate_output.py` shows offending id |
| `MissingRateError` | Foreign currency without prior FX row | Check `exchange_rates.csv` coverage; engine fail-closes (excludes foreign credit) — add rate or document as UNKNOWN |
| `output.csv` 250 rows but validator `OUTPUT-STRUCT` | Column order/count mismatch | Compare header byte-for-byte to `src/affordai/decision/decision.py:OUTPUT_COLUMNS` |
| `77 calls but 0 facts added` | No vendored SDK, `no-backend` fallback | Expected in E0/metered without SDK — decisions byte-identical; add SDK + keys for live LLM |
| `log.txt` not found | First session on new checkout | Created automatically per `AGENTS.md §4` at repo root |
| `pytest` fails on import | Missing `pandas`/`python-dotenv` | `pip install -e ".[dev]"` |
| PowerShell `&&` fails | Win PS 5.1 uses `; if ($?) {}` | Use `; if ($?) { cmd2 }` chaining |

## Script Reference

| Script | Args | Gate |
|---|---|---|
| `scripts/build_output.py` | `--dataset`, `--out` | writes `output.csv` + `usage_report.md` |
| `scripts/validate_output.py` | `--requests`, `--output`, `--dataset` | exit 1 on any hard error |
| `scripts/evaluate.py` | — | local proxy summary |
| `scripts/eval_report.py` | `--tag baseline\|final` | writes `eval_*.json/.md` |
| `scripts/run_ablation.py` | — | writes `ablation_results.*` |
| `scripts/clean_room_run.py` | — | `CLEAN-ROOM PASS/FAIL` |
| `scripts/trace_request.py` | `--request` / `--request-id`, `--dataset` | JSON trace to stdout/file |
| `scripts/benchmark.py` | — | stage timings |
| `scripts/final_red_flag_gate.py` | — | 12 red-flag checks |
| `scripts/final_green_light_gate.py` | — | green-light checklist |
| `scripts/scan_secrets.py` | — | `SCAN CLEAN` |
