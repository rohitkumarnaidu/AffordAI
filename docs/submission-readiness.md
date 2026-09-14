# Submission Readiness — AffordAI (Final Gate, 2026-09-14)

> **Version:** 1.0 · **Last updated:** 2026-09-14 · **Deadline:** `2026-09-13T18:00:00+05:30` (per `AGENTS.md:0` — now passed, but gates still apply)
> **Submission URL (canonical):** `https://www.hackerrank.com/contests/hackerrank-orchestrate-september26/challenges/buy-or-wait/submission` (never homepage)
> All items must be YES. Any red-flag = DO NOT SUBMIT.

## Table of Contents

- [Artifacts](#artifacts)
- [Specification Gate](#specification-gate)
- [Financial Gate](#financial-gate)
- [Evidence Gate](#evidence-gate)
- [Output Gate](#output-gate)
- [Testing Gate](#testing-gate)
- [Reliability Gate](#reliability-gate)
- [Security Gate](#security-gate)
- [Reproducibility Gate](#reproducibility-gate)
- [Red-Flag Gate](#red-flag-gate-any-true--do-not-submit)
- [Final Commands (Copy-Paste)](#final-commands-copy-paste)
- [Known Residuals (Not Blocking)](#known-residuals-not-blocking)

## Artifacts

| Artifact | Location | Requirement | Status 2026-09-14 |
|---|---|---|---|
| `output.csv` | root | 250+header, 8 cols exact order, sorted `original_index` | ✅ 250 rows, header `b'request_id,amount_safe_to_pay,...'` byte-identical `decision.py:OUTPUT_COLUMNS`, mix 33/182/29/6 |
| `code.zip` | root | runnable code + prompts/config + README + `evaluation/` incl. `usage_report.md`; no `.env`/`__pycache__`/`log.txt`/`.git`/secrets | ⚠️ 127 entries `sha3624216e` — **must rebuild** (predates `final_*_gate.py` added post-last-build) |
| `log.txt` | root (gitignored) | append-only, all turns, tool identity exact `tool=opencode`, secrets redacted `[REDACTED]`, UTF-8 LF | ✅ 3535+ lines, shared log, transplanted-correction style preserved |
| `evaluation/usage_report.md` | inside `code.zip` + root `evaluation/` | provider(s)/model(s), calls, in/out/total/avg per request, estimated cost per-model + overall for FINAL run | ✅ metered 77 calls / 7864 tokens / UNKNOWN cost (honest), E0 0/0/0.0000 both documented |

## Specification Gate

- [x] official contract reconciled — `upstream/main:problem_statement.md` + `AGENTS.md §6` mirrored; path dual-layout fixed (verified `dataset` vs `dataset/official` both PASS)
- [x] all required rules documented — spec §§1-10 (inputs/outputs/financial/temporal/evidence/conflict/payment/decision/ranking + failure §9 + prohibited §10)
- [x] output contract documented — 8 cols exact order, 4 statuses + 5 methods, `0≤safe≤requested`, plan `YYYY-MM-DD:amount|…` or `none`, `earliest` empty⇔never safe (decision-matrix §A–G)

Evidence: `docs/specification.md` + `docs/decision-matrix.md` + `docs/data-model.md` (ER + FK tables).

## Financial Gate

- [x] state reconstruction — opening/minimum/requested + `timeline.build_flows` (scheduled/settled + salary confirm, pending-debit reserve)
- [x] currency deterministic — A1 `latest on/before` exact directed pair, `MissingRateError` fail-closed; 140/140 foreign covered
- [x] 90-day simulator — `forecast.simulate` daily ledger `closing≥minimum` every day, `max_safe_today` binary `ROUND_FLOOR`, `earliest_full_date` scan; `WINDOW_DAYS=90, forecast_end=+89`
- [x] payment plans — full/partial(5 gates)/installments(exact match)/wait/`not_recommended` via `generate` + `expand_schedule`
- [x] spending changes — flexible-only ≤3, home-cap FX, must flip `simulate` unsafe→safe
- [x] ranking — 6-tuple `deadline→no-changes→min total→earlier start→fewer payments→lowest option_id` (`None→~~~`)

Evidence: `src/affordai/finance/` 7 modules; `test_sections_15_21.py` 21 tests; `test_sections_12_14_*` temporal/FX boundaries.

## Evidence Gate

- [x] evidence grounded — `interpret` typed 8 kinds only, `resolve_images_for_event` 16↔16 bijections, blank never 0 (`amount_unknown_evidence` conf 0)
- [x] evidence IDs valid + ownership — `EvidenceRegistry` 0 invented; `check_batch_safe` cross-request fail-closed
- [x] contradictions handled — 4-rule precedence `cancel>settle>amend(0>2) → newer sent_at → settled → safer` + LLM-last + lexical
- [x] missing evidence handled — UNKNOWN marker, plan safe without it; per-request `_decide_safe` fallback `not_affordable/none/0` preserving safe/earliest

Evidence: `docs/evidence-and-traceability.md` chain; `test_p0_hardening:12-80` 8 cases; `test_untrusted` 4 injections inert.

## Output Gate

- [x] row count exact — `requests 250 == output 250` ( `wc -l` + `DictReader`)
- [x] row order exact — `req_ids == out_ids` ordered (reverse fails); `RequestContext.original_index` → `serializer` sorted
- [x] schema exact — 8 cols, header byte-match, types `Decimal` 2dp, `YYYY-MM-DD`
- [x] IDs exact — all PKs unique, no duplicate request
- [x] consistency validated — status↔method↔plan↔earliest↔changes↔explanation (`validator.validate_consistency` + `Decision.__post_init__`)

Evidence: `output/validator.py` 6 layers; `scripts/validate_output.py PASS`; 13/13 mutations REJECTED.

## Testing Gate

- [x] unit tests — `tests/unit/` money/FX/forecast/ranking/eligibility/evidence/adapter
- [x] integration tests — `tests/integration/test_chain.py` ingest→decision→validator chain
- [x] regression — `tests/regression/` 15 groups + R01–R06 + `REGRESSIONS.md` catalog (`test_sections_27_30_regression` 15/15)
- [x] adversarial — `tests/adversarial/` 29 threats 5 cats + `test_untrusted` 4 injections (`test_sections_27_30_threats` 29/29)
- [x] end-to-end — `tests/e2e/test_pipeline_e2e.py` 25 sample rows → validated CSV
- [x] edge cases — `tests/edge_cases/test_boundaries.py` floor 0/0.01/minimum/same-day/deadline/window

Evidence: `python -m pytest tests -q` → **375 passed** (2026-09-14).

## Reliability Gate

- [x] retries — bounded transient-only `1+max_retries` (default 1→2 attempts), `MAX_RETRIES_CAP=10`, backoff `min(8,0.5·2ⁿ)` capped
- [x] fallbacks — `FAILURE_MATRIX` 7 failures (timeout/5xx/429/invalid-json/unexpected/missing/image) → empty proposals or UNKNOWN marker → deterministic safe decision, never fabricated
- [x] malformed AI output handling — `_validate_proposal` strict gate (kind/enum/type/range/date/currency/extra-field) + `min_confidence` + `valid_*` IDs
- [x] timeout handling — `call_with_retry` taxonomy, no retry storm (attempts fixed), logged `retry+fallback`
- [x] modality handling — `needs_llm_for_messages` selective, `needs_llm_for_image` linkage-only, non-amount image kinds dropped

Evidence: `src/affordai/evidence/llm_adapter.py:FAILURE_MATRIX` (code authoritative) + `test_sec31_32.py`.

## Security Gate

- [x] no secrets committed — `git log --all -p | grep -i key/token/password` 0 hits outside `redact` patterns + synthetic fixtures
- [x] `.env` ignored — `.gitignore:.env` + `.env.example` placeholders only
- [x] prompt injection protected — typed-fact extractor only, `parse_amount>0` + `event_id` gate, `kind==amount` image filter, deterministic floor unmoved
- [x] external evidence cannot override rules — `pipeline kind==amount` filter + `conflict_resolver` LLM-last + `simulate` + `validator` re-derivation

Evidence: `scripts/scan_secrets.py SCAN CLEAN` 156 files; `docs/threat-model.md` 30.4/30.5 29 cases.

## Reproducibility Gate

- [x] clean-room run — `scripts/clean_room_run.py` fresh subprocess scrubbed env temp-dir → `CLEAN-ROOM PASS`
- [x] deterministic replay — double-run `replay_a == replay_b == output.csv` sha256 `d8386548517835c9` (LF)

Scope honest: fresh-process (not fresh-venv/install) per `docs/reproducibility.md:Clean-Room Procedure` — stdlib-only runtime needs no install.

## Red-Flag Gate (ANY true → DO NOT SUBMIT)

```
[ ] row mismatch · duplicate/missing request · floor violation · fabricated evidence
[ ] invalid schedule · deadline violation · unsupported method · invented installments
[ ] blank amount treated as zero · LLM in arithmetic/ranking · explanation contradicts decision
[ ] secrets committed · transcript missing/malformed · usage report missing · clean-room failure
[ ] unresolved critical regression
```

**Executable gate:** `python scripts/final_red_flag_gate.py` → **ALL CLEAR** (12 checks incl. 250/250 safe+earliest re-derivation + plan re-simulation).

**Executable green-light:** `python scripts/final_green_light_gate.py` → green except `worktree_clean` when this commit’s own files uncommitted (expected until pack).

Full checklist: `docs/build-checklist.md` Modules 0–39 + PH 4+5 verified + MODULE 39 conditional green.

## Final Commands (Copy-Paste)

```powershell
# 1. Install & build
pip install -e ".[dev]"
python scripts/build_output.py --dataset dataset/official --out output.csv

# 2. Validate (must be PASS)
python scripts/validate_output.py --requests dataset/official/requests.csv --output output.csv --dataset dataset/official
python scripts/final_red_flag_gate.py      # expect ALL CLEAR
python scripts/final_green_light_gate.py   # expect green (worktree_clean may be pending)
python scripts/scan_secrets.py             # expect SCAN CLEAN

# 3. Test & repro
python -m pytest tests -q                  # expect 375 passed
python scripts/clean_room_run.py           # expect CLEAN-ROOM PASS
# replay check (in runbook):
python scripts/build_output.py --dataset dataset/official --out replay_a.csv
python scripts/build_output.py --dataset dataset/official --out replay_b.csv
# compare sha256 -> d8386548517835c9 identical

# 4. Package (rebuild — last zip predates gate scripts)
# zip must contain: src/, README.md, evaluation/ (incl. usage_report.md), output.csv — no .env/__pycache__/log.txt/.git
# verify outside repo before submit
```

## Known Residuals (Not Blocking — Documented)

| Residual | Doc | Why Not Blocking |
|---|---|---|
| `code.zip` predates gate scripts | `build-checklist.md:35.2` | Rebuild at pack time; content verified byte-level, clean-room from worktree PASS |
| Image vision never resolves in E0 | `spec §7` + `implementation-status.md:ROW9` | UNKNOWN-safe, plan safe without it — correct per spec |
| FX A1 off-cycle / recurrence ±3% / `code.zip` timing | `spec §7` `[UNPROVEN]` tagged | Fail-closed / conservative — safe direction |
| Partial 0/250 production | `decision-matrix.md §G` table | Synthetic regression covers all 5 gates |
| Official score UNKNOWN | `evaluation/README.md` | Local proxy only — never claimed |

**Verdict: CONDITIONAL GREEN** — every technical gate passes; remaining actions are packaging (`git add` new docs, rebuild `code.zip`, re-run `clean_room_run.py`), not correctness gaps. Submit with `log.txt` (uploaded separately, never in `code.zip`) at the canonical URL above.
