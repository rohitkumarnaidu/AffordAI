# Reproducibility — AffordAI

> **Version:** 1.0 · **Last updated:** 2026-09-14 · **Scope:** Exact steps to reproduce `output.csv` byte-identically from scratch
> Only documents commands that actually work (verified 2026-09-14).

## Table of Contents

- [Environment](#environment)
- [Dependencies](#dependencies)
- [Dataset](#dataset)
- [Deterministic Build](#deterministic-build)
- [Clean-Room Procedure](#clean-room-procedure)
- [Deterministic Replay](#deterministic-replay)
- [Validation Gate](#validation-gate)
- [Evaluation Replay](#evaluation-replay)
- [Artifact Hashes](#artifact-hashes)
- [Known Non-Repro Causes](#known-non-repro-causes)

## Environment

| Item | Value | Verified |
|---|---|---|
| Python | `>=3.11` (tested 3.14.0) | `python --version` |
| OS | Windows 11 (PowerShell 5.1) + POSIX (LF `\n`) | `AGENTS.md §29` |
| Encoding | UTF-8, LF line endings | `data_inventory.md §1` |
| Shell | PowerShell `; if ($?) {}` (not `&&`); `curl.exe` not curl alias | `AGENTS.md §29` |
| Repo branch | `master` | `git branch` → `* master` |
| Repo status | `origin=AffordAI`, `upstream=reference fetch-only`, 0 merges | `git remote -v`, `git log --merges` empty |

## Dependencies

| Group | Packages | Install | Lockfile |
|---|---|---|---|
| **runtime** | `pandas>=2.0`, `python-dotenv>=1.0` | `pip install -e .` | `pyproject.toml:dependencies` |
| **dev** | `pytest>=8.0` | `pip install -e ".[dev]"` | `pyproject.toml:[project.optional-dependencies].dev` |
| **ai (optional)** | `pillow>=10.0` | `pip install -e ".[ai]"` | `pyproject.toml:[project.optional-dependencies].ai` |

No other runtime deps. Standard library only at execution (`hashlib`, `csv`, `decimal`, `datetime`, `pathlib`). If adding a provider SDK, add to `pyproject.toml:ai` and re-run `pip install`.

```powershell
pip install -e ".[dev]"        # E0 deterministic — all you need
pip install -e ".[dev,ai]"     # + vision
# uv lock not used — pyproject.toml + pip is the documented path
```

## Dataset

| Item | Path | Rows | Hash (first 16) | Status |
|---|---|---|---|---|
| `requests.csv` | `dataset/official/requests.csv` | 250 | `f94255baa9f55857` | READ-ONLY, byte-identical `upstream/main:dataset/requests.csv` |
| `sample_requests.csv` | `dataset/official/sample_requests.csv` | 25 | `1195bbe962e62a3e` | Format examples only |
| `financial_profiles.csv` | `dataset/official/financial_profiles.csv` | 275 | `b91b4ccbda3d5af9` | READ-ONLY |
| `financial_events.csv` | `dataset/official/financial_events.csv` | 25342 | `f6a7ccf24d9bfd4a` | 16 blanks ↔16 images |
| `request_payment_options.csv` | `dataset/official/request_payment_options.csv` | 790 | `aedadf63a13f5dd0` |  |
| `exchange_rates.csv` | `dataset/official/exchange_rates.csv` | 134 | `3de3877e48707fea` | 5 directed pairs |
| `messages.csv` | `dataset/official/messages.csv` | 215 | `fd9e3a1acb604f9a` |  |
| `images.csv` + PNGs | `dataset/official/images.csv` + `media/images/*.png` | 16+16 | `c5a3f1686b1f98ac` | 111–756KB each |

`git ls-files -- dataset` and `git show upstream/main:dataset/<file> | sha256sum` byte-identical. During builds, `git diff --stat -- dataset` must be **0**. Derived data → `dataset/generated/` or `evaluation/local/` (gitignored). See `evaluation/reports/data_inventory.md` + `dataset_regression_snapshot.json`.

Dual-layout resolver: `pipeline._resolve_dataset_path` supports `dataset/filename` and `dataset/official/filename` — evaluator may provide either.

## Deterministic Build

E0 config: every `.env` value empty → `LLM_ENABLED != 1` → **0 calls, 0 tokens, cost 0.0000**. Adapter `no-backend` fallback when metered but no SDK.

```powershell
# .env for E0 (deterministic)
# leave EMPTY — default
cat .env.example  # placeholders only; never real keys

# Build (writes output.csv + evaluation/usage_report.md)
python scripts/build_output.py --dataset dataset/official --out output.csv
# → usage report -> evaluation\usage_report.md (77 calls, 7864 tokens)  # metered run still 77 no-backend records; E0 0/0
# → wrote 250 rows -> output.csv in 2.8s
# → status mix: {'affordable_now': 33, 'not_affordable': 182, 'affordable_with_plan': 29, 'affordable_later': 6}

# Metered (optional) — fill .env then rebuild
# LLM_ENABLED=1
# MODEL_PROVIDER=groq
# MODEL_NAME=qwen/qwen3.6-27b
# VISION_MODEL_NAME=groq/compound
# GROQ_API_KEY=...  # never committed
# → 77 calls (66 message_extract + 11 image), 7864 est. tokens, 0 facts added, decisions byte-identical
```

## Clean-Room Procedure

Fresh **process** (not fresh venv) — stdlib-only runtime needs no install (`docs/build-checklist.md:31.1`). Subprocess with scrubbed env (`KEY`/`TOKEN` stripped), temp-dir output, no hidden state.

```powershell
python scripts/clean_room_run.py
# → CLEAN-ROOM PASS (fresh subprocess, scrubbed env, temp-dir, ~3s, validator PASS)
```

Source: `scripts/clean_room_run.py:main` → `sys.executable scripts/build_output.py` + `validate_output.py` with timeout 1200/600. Scope honest: not fresh-venv/install/isolated-copy — documented as fresh-process validation (`evaluation/README.md` vocabulary).

## Deterministic Replay

```powershell
# Double-run must be byte-identical
python scripts/build_output.py --dataset dataset/official --out replay_a.csv
python scripts/build_output.py --dataset dataset/official --out replay_b.csv
python -c "import hashlib; a=open('replay_a.csv','rb').read(); b=open('replay_b.csv','rb').read(); print(hashlib.sha256(a).hexdigest()); print(a==b)"
# → d8386548517835c9…  True
# also:
# production_hash 620bff42124b0c3d (pipeline determinism), mix 33/182/29/6 stable

# Also verified:
python -c "import csv; r=set(r['request_id'] for r in csv.DictReader(open('dataset/official/requests.csv'))); o=set(r['request_id'] for r in csv.DictReader(open('output.csv'))); print(r==o)"
# → True, ordered
```

Stability guarantees: `pipeline.py` sorted `original_index`, `optimizer.rank_key` 6-tuple, `money.quantize` `ROUND_FLOOR`, `serializer.decisions_to_rows` ordered + duplicate-PK guard.

## Validation Gate

```powershell
python scripts/validate_output.py --requests dataset/official/requests.csv --output output.csv --dataset dataset/official
# → PASS (structural + plan)

# Red-flag + green-light gates (added 2026-09-13, 14 tests)
python scripts/final_red_flag_gate.py
# → ALL CLEAR  (12 checks incl. 250/250 safe+earliest re-derivation + plan re-simulation)

python scripts/final_green_light_gate.py
# → green except worktree_clean when this turn has uncommitted files (expected)

python scripts/scan_secrets.py
# → SCAN CLEAN (156 files; header-only fixture rule proven)
```

Any `ValidationError` → `exit 1` **blocks submission** (`AGENTS.md §16`).

## Evaluation Replay

```powershell
python -m pytest tests -q
# → 375 passed (unit/integration/edge/adversarial/regression/e2e/contract/security)

python scripts/evaluate.py
python scripts/eval_report.py --tag final
python scripts/run_ablation.py   # E0→E7, 23s

# Reports (LOCAL PROXY — NOT official score):
# evaluation/reports/eval_baseline.{json,md}, eval_final.{json,md}
# evaluation/reports/ablation_results.{json,md} — Version | Decision Acc | Plan Acc | Evidence | Invalid | Tokens | Cost | Runtime  +  Component | Benefit | Cost | New Failures | Decision (KEEP/REMOVE)
# ablation: E0 0.40/0.40 11ev, E1 0.44/0.48 11ev, E2 0.44/0.48 0ev, E3 132/250 facts, E5 250/250 consistent, E6 all controls caught, E7 0 tokens — decisions KEEP with deltas documented
```

Official HackerRank score = UNKNOWN (`evaluation/README.md` mandatory vocabulary). Local proxy `0.44/0.48` vs `sample_requests.csv` is illustrative only.

## Artifact Hashes

| Artifact | Hash / Size | Verified |
|---|---|---|
| `output.csv` replay | `sha256 d8386548517835c9f542278d426dcd815edebf921b12292d5f1be87b480f8bca6` ( LF) | double-run 2026-09-14 |
| `output.csv` inside code.zip | same (normalized LF) | `sections-33-35-report.md` |
| `code.zip` last | 127–129 entries, 477KB | `git ls-files` 14 docs; must be rebuilt after gate scripts added |
| Dataset snapshot | `evaluation/reports/dataset_regression_snapshot.json` | `f94255ba…` etc. |
| Learners | `docs/Learnings/README.md` 10 hashes distinct | SHA `dbc6bb4…` etc. |
| Commit | `427372d` (docs polish) | `git log --oneline` |

## Known Non-Repro Causes

| Cause | Why Not Repro | Mitigation |
|---|---|---|
| **Metered additives not installed** | No vendored SDK → `no-backend` records, 0 facts, byte-identical but usage_report differs (0/0 vs 77/7864) | Both truths documented (`README §9`, `evaluation-strategy §28`); decisions identical |
| **PowerShell CRLF vs POSIX LF** | `serializer` writes LF `\n`, git warns `LF will be replaced by CRLF` on checkout | Normalized LF compare (`--` in hash calc uses binary) |
| **Stale `code.zip`** | Zip predates `final_*_gate.py` added 2026-09-13 | Rebuild at pack time: `python -m zipfile -c code.zip ...` or `scripts/` pack step |
| **`uv.lock` absent** | `pyproject.toml` is source of truth, not `uv.lock` (not committed) | `pip install -e ".[dev]"` is documented path |
| **`dataset/` vs `dataset/official/`** | Evaluator may provide either | Dual-layout resolver handles both |

Cross-doc: `docs/architecture.md` (deterministic boundaries), `docs/implementation-status.md` (subsystem PASS/PARTIAL), `docs/runbook.md` (script reference), `evaluation/README.md` (OFFICIAL vs LOCAL).
