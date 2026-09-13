# Master Inspection Report — AffordAI (Buy or Wait?) — 2026-09-13

> Scope: inspection / understanding phase only — no financial engine built in this turn.
> Method: Tier 1 (official `problem_statement.md` + `AGENTS.md §6`) > Tier 2 (local repo + dataset) > Tier 4/5 (Learnings). All 10 Learnings read in parallel; every CSV + all 16 images inventoried; git/log/source/validators checked. `INFERENCE` vs `LOCAL MEASUREMENT` marked explicitly.

---

## SECTION A — Repository State

- **Branch:** `master` (no worktree, HEAD = `b0a8898`).
- **Remotes:** `origin → rohitkumarnaidu/AffordAI`, `upstream → interviewstreet/hackerrank-orchestrate-september26` — `git remote -v` verified. `upstream/main` at `a7b9744`, fetched only, **never pulled/merged** (INVARIANT OK).
- **Status (2026-09-13 12:3x IST):** clean before this inspection; 5 new untracked files in `docs/Learnings/` (the Sept build-contract, opencode inspection prompt, winning checklist, September master merge, integrated research) appeared after `b0a8898`. Now indexed via `docs/Learnings/README.md` (added this turn, not yet committed).
- **Commit count:** 6 on `master`: `90fd34d` init skeleton → `6047967` spec docs → `0feefe8` dataset + inventory → `d895a11` prior Learnings → `1f2c063` final AGENTS.md (322 lines, 30 sections) → `b0a8898` hierarchy alignment + build-checklist.
- **Tree:** `AGENTS.md`, `README.md`, `.gitignore` (covers `.env` + `log.txt` + `dataset/local/` etc.), `.env.example`, `pyproject.toml`, `docs/{specification,decision-matrix,data-model,architecture,evaluation-strategy,threat-model,interview-notes,build-checklist}.md`, `docs/Learnings/` (10 files + new README), `src/affordai/{ingestion,evidence,finance,decision,output,evaluation,observability,pipeline}.py` (skeleton, 3 determinist files live), `scripts/{build_output,validate_output,evaluate,clean_room_run}.py`, `tests/unit/test_contract_invariants (3 passed)`, `dataset/official/` (9 CSVs + 16 PNGs), `evaluation/{usage_report template, reports/data_inventory}`.

## SECTION B — Documentation State

- **Present (8/8):** all required docs exist. `specification.md` (114 lines) correctly mirrors Tier 1; `decision-matrix.md` captures partial 5-conds + 6-rule rank; `data-model.md` joins + nullability; `architecture.md` deterministic-vs-AI split; `evaluation-strategy.md` (LOCAL PROXY label); `threat-model.md` (injection + conflict + missing-FX); `interview-notes.md` skeleton; `build-checklist.md` (183 lines, Modules 0–35). **AGENTS.md** final contract at 30 sections — verified against all required keywords (prompt injection, `tool=`, `original_index`, FX A1, submission URL).
- **Learnings:** 10 distinct files (SHA check 10/10 unique), now indexed via `docs/Learnings/README.md` mapping each file to Tier 4/5 and to its descendant in the live docs. No duplicates created; `AffordAI_Orchestrate_…` vs `Orchestrate_Integrated_Master_Research` are *not* duplicates (101724 vs 67558 bytes, hashes e2f4778 vs 7b720b44) — the former is the deduplicated merge, treated as canonical research going forward.
- **Missing / gaps:** `interview-notes.md` still a skeleton (per-component WHAT/WHERE/WHY + live walkthrough not yet populated — expected at Milestone 2). `README.md` current (purpose/architecture/AI-boundary/run) but not yet expanded with limitations + token section (Milestone 5). No contradictions detected between `specification.md`, `decision-matrix.md`, and `AGENTS.md §11` — all derive from the same Tier 1 read.

## SECTION C — Official Challenge State

- **Files read:** `upstream/main:problem_statement.md` (162 lines, §6.3 contract + §6.5 token report) and `upstream/main:AGENTS.md` (log path, session-start/per-turn formats, `tool=` rule, submission link rule) via `git show`, plus `code/main.py` (empty starter) and `dataset/` manifest via `git ls-tree`. Official README confirms `dataset/media/images/<image_id>.png` mapping.
- **Rules captured:** 8-col output schema + exact order + 250 rows, row-order = input order, statuses/methods enums + `partial⇒affordable_with_plan` constraint, partial exact 2-payment sum, installments exact-match, spending ≤3 flex-only + stop/reduce exclusive, 90-day `closing >= minimum` invariant on every projected day + deadline gate, 6-rule ranking (deadline → no-changes → min-total → earlier-start → fewer-payments → lowest option_id), 4-rule conflict precedence, blank amount → image (never zero), dated FX on `settlement_date` with exact directed pair, messages/images untrusted, token report + evaluation separation.
- **Unresolved ambiguities (all documented, none blocking Milestone 2):**
  1. **FX fallback A1:** 5 directed pairs only; latest row ≤ settlement for exact pair is the implemented policy — if a pre-window foreign event has no prior row, the engine will fail-closed (exclude credit, keep debit) and log. Needs one engine test to lock.
  2. **Recurrence detection cadence:** no explicit `frequency` column; must be inferred from per-user history day-of-month clustering — characterize during ingestion.
  3. **Image OCR fallback:** extraction confidence < threshold → treat amount as unknown → plan must stay safe without it (never fabricate) — vision prompt + validator to codify in E2.
  4. **IDR rounding:** 0-decimal vs 2-decimal display convention — confirm from sample `amount_safe_to_pay` formatting before serializer.

## SECTION D — Dataset State

| File | Rows | Cols | PK / Grain | Nulls / notes | Dates / range |
|---|---|---|---|---|---|
| `requests.csv` | 250 | 8 | `request_id` | none blank | `2023-01-20 → 2026-09-04`; avg requested ~ varied by type |
| `sample_requests.csv` | 25 | 15 | `request_id` | solved outputs filled | same range; status mix 9 with_plan / 7 not_aff / 6 later / 3 now |
| `financial_profiles.csv` | 275 | 10 | `user_id` (250 eval + 25 sample-only) | `max_installment_months` blank 119 | home: INR 67 / EUR 62 / IDR 55 / ZAR 51 / USD 40 |
| `financial_events.csv` | 25342 | 14 | `event_id` | `amount` blank **16** (= images); `linked_event_id` 58; `minimum_allowed_amount` 2907 | `2023-10-02 → 2026-11-15` settlement |
| `request_payment_options.csv` | 790 | 9 | `payment_option_id` | `payment_frequency_days` blank 275 (= full) | 2/3/4 per req (65/180/30) |
| `exchange_rates.csv` | 134 | 4 | (`rate_date`, `from→to`) | no nulls | 39 dates `2023-10-15 → 2026-11-15` + extra `2025-10-01` |
| `messages.csv` | 215 | 7 | `message_id` | `request_id` blank 87 (user-level), `related_event_id` 39 | 5 sources: employer 126 / service 31 / fin 23 / bank 18 / merchant 17; multilingual EN + ID |
| `images.csv` | 16 | 4 | `image_id` | all mapped | 16 PNGs present, 186KB–756KB |
| `output.csv` (template) | 250 | 8 | `request_id` | all blank predictions | shape only |

- **Joins:** `requests.user_id → profiles.user_id` 1:1; `requests → payment_options` 1:2–4; `requests → messages` 1:n + user-level messages; `financial_events.event_id ↔ messages/images.related_event_id` 1:n; `linked_event_id` chain length 1 (58 pairs, e.g. refund `event_99→98`, valuation `event_1856→1855`); no orphan `request_id`s found; image linkage **16↔16 exact** (every blank `event_id` maps to exactly one `image_id` — INFERENCE: seller supplied 1:1 coverage, no missing-image case in eval).
- **Unusual cases:** 16 blank amounts cover all 5 currencies and all 4 non-failed statuses (settled/scheduled/pending) — blank ≠ status signal. 58 linked pairs include settled refunds and `unrealized` valuations (to be excluded from cash flow). No injection strings (`ignore`/`override`) in messages — LOCAL MEASUREMENT.

## SECTION E — Image State

- **Count:** 16 rows in `images.csv`, 16 files in `dataset/official/media/images/` — 1:1, no missing files. Sizes 112KB–756KB, all PNG.
- **Mapping:** `event_253→image_01 (user_03)` … `event_10521→? (user_113)` — every blank maps to its `related_event_id` partner. Also covers 1 income (user_03) + 15 expenses across 16 distinct users.
- **Relevance:** All 16 are amount-carriers (the challenge-critical blank cases). Non-blank events with images: 0 in eval — image handling in eval is exclusively blank-recovery.
- **Extraction plan (no fabrication):** E2 vision call only on these 16 rows; prompt extracts `amount + currency + confidence`; validator checks file exists, owner matches (`user_id` + `request_id`), amount plausible (>0, not absurd scale), currency consistent with event. On low confidence / missing file, degrade to unknown → plan stays safe without the amount, log as `image_unreadable`, never treat as 0. OCR values NOT pre-written — they will come from the metered run and be reflected in `evaluation/usage_report.md`.

## SECTION F — Deterministic Core

- **Required modules (per spec + AGENTS.md §20):** `ingestion/{requests,profiles,events,messages,images,payment_options}` → canonical `RequestContext` (`pipeline.py`) → `evidence/registry` → `finance/{state,currency,timeline,forecast,payment_plans,spending_changes,optimizer}` → `decision/{decision,eligibility,invariants,rules}` → `output/{explanation,serializer,validator}`. Skeleton exists; live files are `decision/decision.py` (canonical object + enums), `decision/invariants.py` (bounds + status/method/earliest consistency), `output/validator.py` (structural layer), `pipeline.py` (`RequestContext`), `scripts/build_output` (placeholder 250-row skeleton, validates structurally), `scripts/validate_output`.
- **Exact responsibilities (per build-checklist Modules 9–21):** ingestion = typed loads + `original_index`; currency = A1 directed conversion; timeline = settlement-day ledger + recurrence inference; forecast = daily `opening+inflows-essentials-recurring-existing+plan=closing` with `closing>=minimum` every day + deadline; payment_plans = generate 6 shapes then safety→deadline→preference→ranking; invariants = re-simulation gate; optimizer = fixed 6-rule deterministic sort.
- **Open questions for Milestone 2:** recurrence window length; pre-window FX concrete handling; IDR rounding; vision fallback threshold. All are narrow engine tests, not spec gaps — DO NOT guess.

## SECTION G — AI Boundary

- **AI-allowed (3 gates):** message semantics (cancel/settle/amend/delay/confirm/amount/date/preference), image amount extraction (16 rows only), grounded explanation drafting from validated `Decision` facts.
- **Must be deterministic (hard gate):** arithmetic, date math, FX, 90-day simulation, payment-plan math, deadline/minimum validation, eligibility, ranking/tie-breaks, schema enforcement. The repo enforces this via file separation + `AGENTS.md §12` + the skeleton's module names.
- **Prohibited (tested adversarially):** LLM arithmetic, LLM ranking, LLM minimum-balance override, untrusted evidence overriding precedence. `threat-model.md` + future `tests/adversarial/` cover injection→typed-facts-only.

## SECTION H — Validation

- **Live:** `src/affordai/decision/invariants.py` (3 checks), `src/affordai/output/validator.py` (column/order/count/order/duplicate/bounds/status/method/earliest), `scripts/validate_output.py` (exit 1 on failure). Placeholder `build_output` passes structural validation; blank template correctly rejected — LOCAL MEASUREMENT.
- **Tests:** `tests/unit/test_contract_invariants.py` — 3 cases, **all pass** (`pytest 3 passed`). `tests/regression/test_regression_placeholder.py` empty bucket.
- **Pending (Milestone 2 gates):** financial re-simulation, plan chronology, spending-changes flex-only/≤3, evidence ID ownership, decision↔explanation consistency — tracked in `build-checklist.md` Module 22 (§22.2 `~`).

## SECTION I — Evaluation

- **Local proxy (NOT official score):** `docs/evaluation-strategy.md` defines structural/numerical/decision/plan+safety/evidence/explanation dimensions + ablation table E0–E7. `scripts/evaluate.py` currently a stub; Milestone 2 implements 25-sample scoring.
- **Baseline E0:** deterministic skeleton (typed ingestion + forecast without messages/images). E1 = +messages, E2 = +images (16 rows), E3 = conflicts, E4 = optimizer, E5 = explanations, E6 = validation, E7 = token trim. Keep only measured wins.
- **Ablation reporting:** results → `evaluation/reports/`, final metered run → `evaluation/usage_report.md` (template live).

## SECTION J — Transcript

- **Path:** `<repo root>/log.txt` = `C:\Hackathons\Hackerrank\AffordAI - AI Financial Affordability & Payment Planner\log.txt` (per `AGENTS.md §4`, gitignored — `git check-ignore log.txt` confirmed, `log.txt` itself ignored).
- **Exists:** yes. Contains `SESSION START` at `2026-09-13T12:20:11+05:30` (`tool=opencode`, 5h39m remaining) + one per-turn entry `Finalize AGENTS.md` (`2026-09-13T12:35`) — both valid, tool identity exact, secrets redacted, UTF-8, append-only.
- **Logging function:** working — this inspection will append as its per-turn entry; after that every user turn appends per `AGENTS.md §6`.
- **History:** logging began at `12:20` after 4 commits; earlier turns (repo init, spec, inventory) predate the contract. **Decision:** do NOT fabricate them. The log stays as-is; this report notes the gap transparently. Future sessions are fully covered. If a judge asks about pre-12:20 work, point to `git log` (90fd34d→b0a8898) as the evidence trail.
- **Reconstruction needed:** none — no rewrite, no truncation, no second log.

## SECTION K — Risk Register

| Risk | Likelihood | Impact | Detectability | Mitigation | Status |
|---|---|---|---|---|---|
| Row-order corruption (prior failure) | Medium | CRITICAL (global) | output validator | `original_index` preserved; sort at serializer; validator `input_ids==output_ids` order; double-run diff | skeletons done, engine test pending |
| Blank→image missed (16 rows) | High | High | FX/plan tests | image resolver only path; on fail, unknown→safe degrade, never 0 | E2 gated |
| FX missing rate / pre-window | Low | High | currency tests | A1 policy + fail-closed + logged | policy set, test pending |
| Message mis-read / injection | Medium | Medium | evidence validator | typed facts + provenance + untrusted-data gate; injection tests | planned E1 |
| Recurrence double-count | Medium | High | forecast tests | per-user history inference + single-count guard | char pending M2 |
| Preference bypass | Low | Medium | eligibility tests | `will_consider` + `max_months` gate before ranking | planned |
| Spending-change illegal | Low | Medium | plan validator | flexible-only + ≤3 + stop/reduce exclusive | planned |
| Blank amount treated as 0 | Low | CRITICAL | budget tests | single choke: image resolver, validator rejects 0 fallback | enforced |
| LLM in arithmetic/ranking | Low | CRITICAL | architecture boundary + code review | file separation + AGENTS.md §12; ablation keeps | enforced |
| Transcript incompleteness | Low | Medium | git log | disclosure + continuous logging from now | mitigated |
| Clean-room drift | Medium | High | `clean_room_run` | fresh env, no hidden state, usage report metered | script stub, M2 impl |

---

## GO / NO-GO — Milestone 2 Gate

### GO — proceed to Milestone 2

`GO` because: official contract is fully captured in `docs/specification.md` + `AGENTS.md §11` (verified against Tier 1); dataset understood to row/column/join/image precision (Section D/E) with the 16↔16 blank mapping locked; the 4 open ambiguities are narrow engine tests, not spec holes; deterministic core is specified module-by-module (AGENTS.md §20) with the right invariants; AI boundary is crisp; validation strategy is staged (structural live, financial/plan next); transcript is functioning and disclosed; Milestone 2 scope is bounded.

### NO-GO would trigger if

- a Tier 1 rule were unknown → false, spec is complete.
- a join/blank linkage were unresolved → false, 16↔16 exact.
- the 90-day invariant or ranking were undefined → false, both pinned (§4 + decision-matrix D).
- transcript were broken → false, append-only and `git check-ignore` green.
- implementation would require guessing → false, only 4 narrow tests remain (FX pre-window, recurrence cadence, OCR threshold, IDR rounding).

---

## Milestone 2 — Exact Next Build Sequence (bounded tasks)

> Execute in order; stop for review before any LLM. Each task = `SPEC → PLAN → IMPLEMENT → TEST → INSPECT → FIX → REGRESSION → VERIFY` per AGENTS.md §28.

1. **Typed ingestion + identity** (`src/affordai/ingestion/*.py`) — load 9 files, validate schemas, stamp `original_index`, enforce `request_id/user_id` ownership, join to `RequestContext`. Tests: schema, null, row-count, identity preservation. *Fixes Module 2–4 gates.*
2. **Currency engine** (`finance/currency.py`) — implement A1 dated conversion + `usage_report` FX log. Tests: same-currency, each of 5 foreign pairs, pre-window fail-closed. *Fixes Module 9.*
3. **Temporal engine** (`finance/timeline.py`) — date ledger, request-day treatment, settlement-day cash movement, recurrence inference from history. Tests: same-day, deadline-day, 90-day boundary, recurrence anomaly. *Fixes Module 10.*
4. **90-day forecast** (`finance/forecast.py` + `state.py`) — daily `opening/inflows/essentials/recurring/existing+plan=closing` with `closing>=minimum` every day; pending-debit reserve vs pending-credit ignore; confirmed salary on settlement. Tests: exact floor, floor±1, late income, floor violation. *Fixes Modules 11–12, 14–15.*
5. **Candidate plans + invariants** (`finance/payment_plans.py`, `spending_changes.py`, `decision/invariants.py`) — generate full/partial/install/wait/none, validate partial 5-conds + spending ≤3 flex-only, re-simulate every candidate. Tests: plan totals, chronology, deadline, preference. *Fixes Modules 13, 16–18.*
6. **Eligibility + ranking** (`decision/eligibility.py`, `finance/optimizer.py`) — `will_consider` + `max_months` gate, then deterministic 6-rule sort with `payment_option_id` final tie-break. Tests: each tie-break layer. *Fixes Modules 19–20.*
7. **Canonical decision + serializer** (`decision/decision.py`, `output/serializer.py`) — `Decision` → CSV sorted by `original_index`. *Fixes Module 21–22.1.*
8. **Extend validators + 25-sample evaluation** (`output/validator.py`, `decision/invariants.py`, `scripts/evaluate.py`) — financial/plan/date/evidence/consistency layers; score 25 solved samples as LOCAL PROXY, grouped by rule. *Fixes Module 22.2 + 25.*
9. **STOP for review** — run full suite: `pytest` + `validate_output` on 25 samples + double-run determinism + build-checklist Modules 2–22 tick. Only then consider E1 (messages) one component at a time.

**First bounded coding task → Task 1 (typed ingestion).** Prompt: “Implement typed loaders in `src/affordai/ingestion/` per `docs/specification.md §2` + `docs/data-model.md`, preserve `original_index+request_id+user_id` on every row, build `RequestContext` in `pipeline.py`, add `tests/unit/test_ingestion_identity.py` covering row-order, ownership, blank-amount passthrough, and null handling, run `pytest` and report failures before any finance logic.”
