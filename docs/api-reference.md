# API Reference — AffordAI `src/affordai/`

> **Version:** 1.0 · **Last updated:** 2026-09-14 · **Entry point:** `scripts/build_output.py` → `src/affordai/pipeline.py:run`

## Table of Contents

- [Module Map](#module-map)
- [Pipeline (`pipeline.py`)](#pipeline-pipelinepy)
- [Ingestion (`ingestion/`)](#ingestion-ingestion)
- [Evidence (`evidence/`)](#evidence-evidence)
- [Finance (`finance/`)](#finance-finance)
- [Decision (`decision/`)](#decision-decision)
- [Output (`output/`)](#output-output)
- [Evaluation (`evaluation/`)](#evaluation-evaluation)
- [Observability (`observability/`)](#observability-observability)
- [Scripts](#scripts)

## Module Map

```
src/affordai/
├── pipeline.py               # Orchestrator: build_contexts → decide_context → Decision → CSV
├── ingestion/                # Typed CSV loaders, dedupe, dual-layout resolver
│   ├── __init__.py           # require_decimal, parse_amount_safe, DatasetError
│   ├── requests.py           # load_requests
│   ├── profiles.py           # load_profiles
│   ├── events.py             # load_events
│   ├── payment_options.py    # load_payment_options
│   ├── exchange_rates.py     # load_exchange_rates → RateTable
│   ├── messages.py           # load_messages
│   └── images.py             # load_images, resolve_images_for_event
├── evidence/
│   ├── evidence_registry.py  # Evidence, EvidenceRegistry, provenance
│   ├── message_interpreter.py# interpret(message) → list[Evidence]
│   ├── message_income.py     # confirmed_series(salary) narrow confirm
│   ├── image_interpreter.py  # resolve_images_for_event, amount_unknown_evidence
│   ├── conflict_resolver.py  # resolve, cancelled_set, amended_amounts/dates
│   └── llm_adapter.py        # propose_facts, MODEL_CALLS, FAILURE_MATRIX
├── finance/
│   ├── money.py              # Decimal quantize, parse_amount
│   ├── currency.py           # RateTable.get_rate, convert_to_home (A1)
│   ├── temporal.py           # WINDOW_DAYS=90, forecast_end, clamp_month_day, meets_deadline
│   ├── timeline.py           # build_flows (scheduled/settled + salary confirm)
│   ├── state.py              # FinancialState, build(opening/minimum/flows)
│   ├── forecast.py           # simulate, max_safe_today, earliest_full_date
│   ├── payment_plans.py      # generate, expand_schedule
│   ├── spending_changes.py   # candidate_targets, find_variants
│   └── optimizer.py          # rank_key, select (6-rule)
├── decision/
│   ├── decision.py           # Decision (frozen), OUTPUT_COLUMNS, to_serialized_row
│   ├── invariants.py         # check_earliest_consistency, validate_*_strict
│   ├── eligibility.py        # filter_candidates (preference/term gate)
│   └── rules.py              # derive(status, method) mapping
├── output/
│   ├── serializer.py         # decisions_to_rows, format_plan, write_output_csv
│   ├── explanation.py        # build, build_facts, validate, build_fallback
│   └── validator.py          # validate_files/plans/evidence/consistency/safety/validate_all
├── evaluation/
│   ├── metrics.py            # METRIC_DEFS, full_dataset_metrics, categorize_errors
│   ├── harness.py            # run_dataset
│   ├── ablation.py           # VERSION_DEFS, run_input_version, instrument_*
│   └── usage.py              # UsageReport, ModelCallRecord, PRICING, to_markdown
└── observability/
    ├── tracing.py            # Trace (legacy)
    └── request_trace.py      # RequestTrace, make_trace_id, RequestTraceStore
```

## Pipeline (`pipeline.py`)

| Symbol | Signature | Purpose |
|---|---|---|
| `RequestContext` | `dataclass(original_index, request_id, user_id, request, profile, events, messages, images, payment_options, evidence)` | Canonical per-request container, preserves `original_index` |
| `build_contexts(tables, dataset_dir)` | `-> list[RequestContext]` | Indexed joins `by_user/by_request`, dedupe PK, sorted `events(settlement_date,event_id)` `messages(sent_at,message_id)` |
| `_resolve_dataset_path(dataset_dir, filename)` | `-> Path` | Dual-layout `dataset/filename` → `dataset/official/filename` fallback |
| `_dedupe_by_key(rows, key)` | `-> list[dict]` | PK dedupe, raises `DatasetError` |
| `_collect_evidence(ctx, tables)` | `-> (EvidenceRegistry, Trace)` | `interpret` → selective `propose_facts` → `add` (ownership) → `resolve` → salary linkage |
| `decide_context(ctx, RateTable)` | `-> Decision` | `build_flows → build_state → max_safe/earliest → generate → filter → simulate → select → Decision → explanation` |
| `_decide_safe(ctx, RateTable)` | `-> Decision` | Per-request fallback `not_affordable/not_recommended/none/0` preserving safe/earliest when derivable |
| `run(dataset_dir, out_path)` | `-> (decisions, usage)` | Full 250-row run, sorted by `original_index`, writes CSV |

## Ingestion (`ingestion/`)

| Loader | Returns | Null Handling |
|---|---|---|
| `load_requests(path)` | `list[dict]` | `requested_amount` Decimal, `allows_partial` bool |
| `load_profiles(path)` | `dict[user_id → dict]` | `max_installment_months` blank → `None` |
| `load_events(path)` | `list[dict]` | `amount` blank → `None` (never 0), `settlement_date` blank → `None` |
| `load_payment_options(path)` | `dict[request_id → list[dict]]` | `payment_frequency_days` blank → `None` |
| `load_exchange_rates(path)` | `RateTable` | composite PK `(date,from,to)` unique |
| `load_messages(path)` | `list[dict]` | `request_id/related_event_id` nullable |
| `load_images(path)` | `list[dict]` | file existence checked downstream |

All loaders: UTF-8, LF, comma, header-exact, `len(row)==len(header)` guard, typed Decimal/dates.

## Evidence (`evidence/`)

| Symbol | Signature | Purpose |
|---|---|---|
| `Evidence` | `dataclass(source_type, source_id, request_id, user_id, event_id?, message_id?, image_id?, raw_value, normalized_value, confidence, method, sent_at?)` | Provenance-carrying fact |
| `EvidenceRegistry(valid_event_ids, valid_message_ids, valid_image_ids)` | `.add(Evidence) → bool` | Ownership + allowlist + confidence [0,1] gate; `EvidenceError` on bad id |
| `interpret(message)` | `dict → list[Evidence]` | Regex typed facts only; never financial decisions |
| `confirmed_series(messages)` | `list[dict] → list[(date,Decimal)]` | Narrow salary confirm (employer+confirm+salary keywords, deny-first) |
| `resolve_images_for_event(event_id, image_rows, media_dir)` | `-> list[{image_id,path,file_exists}]` | 16↔16↔16 bijection |
| `amount_unknown_evidence(event_id, request_id, user_id)` | `-> Evidence` | `kind=amount, confidence=0, normalized=unknown` |
| `resolve(facts)` | `list[Evidence] → (cancelled_set, amended_amounts, amended_dates, conflicts)` | 3-pass stable sort: cancel>amend(0>2) → newer `sent_at` → settled → safer + LLM-last + lexical |
| `propose_facts(purpose, payload, ctx)` | `-> list[Evidence]` | Bounded, schema-validated, `min_confidence` gated, `no-backend` fallback when `LLM_ENABLED!=1` |

`MODEL_CALLS` dict in `llm_adapter.py` mirrors `docs/model-call-inventory.md` (code authoritative).

## Finance (`finance/`)

| Symbol | Signature | Purpose |
|---|---|---|
| `quantize(amount, currency)` | `Decimal → Decimal` | `ROUND_FLOOR` 2dp for all 5 currencies |
| `RateTable.get_rate(from, to, settlement_date)` | `-> Decimal` | **A1**: latest row on/before settlement, exact directed pair; `MissingRateError` fail-closed |
| `forecast_end(request_date)` | `date → date` | `request_date + 89` (90 days inclusive) |
| `build_flows(events, messages_evidence, profile, request_date)` | `-> list[Flow]` | Scheduled/settled + salary confirm; pending debit reserved, credit ignored; 10 unrealized fallback `event_date` then ignored |
| `build(state)` | `(opening, minimum, requested, flows) → FinancialState` | Validates bounds, guards double-count |
| `simulate(state, payments, changes)` | `-> SimulationResult(ok, reason, daily_closings)` | Daily ledger `closing ≥ minimum` every day + deadline |
| `max_safe_today(state)` | `-> Decimal` | Binary search `ROUND_FLOOR hi`, `0 ≤ safe ≤ requested`, BEFORE changes |
| `earliest_full_date(state)` | `-> date\|None` | Forward scan first safe single-payment date, preference-independent |
| `generate(state, options, safe, earliest, allows_partial)` | `-> list[Candidate]` | Full/partial(5 gates)/installments(exact)/wait candidates |
| `expand_schedule(option)` | `dict → list[(date,Decimal)]` | Exact dates/amounts from option |
| `candidate_targets(profile, events)` | `-> list[Target]` | Flexible-only, protected kept, ≤3, stop/reduce exclusive |
| `find_variants(state, candidates)` | `-> list[Candidate]` | Must flip `simulate` unsafe→safe + deadline |
| `rank_key(candidate, deadline)` | `-> tuple` | 6-tuple: deadline→no-changes→min total→earlier start→fewer payments→lowest option_id (`None→~~~`) |

## Decision (`decision/`)

| Symbol | Signature | Purpose |
|---|---|---|
| `Decision` | `frozen dataclass(request_id, amount_safe_to_pay:Decimal, affordability_status, recommended_payment_method, payment_plan, earliest_date_for_full_payment, spending_changes_needed, decision_explanation, evidence, explanation_facts)` | Canonical 8-field object, `__post_init__` enforces `0≤safe≤requested` + enums + consistency |
| `OUTPUT_COLUMNS` | `tuple[8]` | `request_id,amount_safe_to_pay,...` exact order |
| `derive(winner)` | `Candidate\|None → (status, method)` | `full→now, partial/installments+changes→with_plan, wait→later, None→not_affordable/not_recommended` |
| `filter_candidates(candidates, profile)` | `-> list[Candidate]` | Preference/term gate BEFORE simulation |
| `check_earliest_consistency(status, earliest, request_date)` | `-> bool` | `affordable_now ⇒ earliest==request_date`, empty⇔never safe |

## Output (`output/`)

| Symbol | Signature | Purpose |
|---|---|---|
| `decisions_to_rows(decisions, home_by_request)` | `-> list[dict]` | Sorted `original_index`, duplicate-PK guard, 8-col exact, Decimal 2dp, `YYYY-MM-DD` |
| `format_plan(payments)` | `-> str` | `YYYY-MM-DD:amount\|...` or `none` |
| `write_output_csv(rows, path)` | `-> Path` | `QUOTE_MINIMAL`, LF `\n` |
| `build(decision, requested, request_date, home)` | `-> str` | `WHY+CONSTRAINT+PLAN+TIMING+EVIDENCE` from validated facts only |
| `validate(text, decision)` | `-> bool` | No invented amounts/dates/evidence/contradiction |
| `validate_all(requests, output, options, profiles, decisions, contexts)` | `-> list[ValidationError]` | 6 layers, structured `OUTPUT-STRUCT/ID/NUM/ENUM/PLAN/SPEND/EVIDENCE/CONSISTENCY` |
| `validate_files/plans/evidence/consistency/safety/canonical` | `-> list[ValidationError]` | Per-layer re-derivation |

`scripts/validate_output.py` exits 1 on any hard error (submission blocker).

## Evaluation (`evaluation/`)

| Symbol | Signature | Purpose |
|---|---|---|
| `METRIC_DEFS` | `dict[metric → {definition, numerator, denominator, pass_fail, official_or_local, truth_source}]` | 9 metrics (structural..cost) |
| `full_dataset_metrics(decisions, contexts)` | `-> dict` | 0 errors across 6 correctness layers |
| `run_dataset(dataset_dir)` | `-> Report` | Harness for 5 sets |
| `VERSION_DEFS` | `dict[E0..E7]` | Ablation versions + instruments |
| `UsageReport` | `dataclass(provider, model, calls, in/out/total/avg/cost)` | + `to_markdown()`, `PRICING` separate |
| `ModelCallRecord` | `dataclass(request_id, provider, model, purpose, in/out, token_source, success, retry, fallback)` | Per-attempt accounting |

## Observability (`observability/`)

| Symbol | Signature | Purpose |
|---|---|---|
| `RequestTrace` | `dataclass(trace_id, original_row_index, facts, candidates, rejected_plans, selected, status)` | 10-section per-request trace |
| `make_trace_id(run_id, request_id, index)` | `-> str` | `sha256(run\|request\|index)[:16]` deterministic |
| `Trace` | `class` | Legacy global trace (request_id + message, no secrets) |

`scripts/trace_request.py --request <id>` emits JSON; `pipeline.run` populates `request_traces` dict when supplied.

## Scripts

See `docs/runbook.md#script-reference` for CLI args and gates. All scripts: `python scripts/<name>.py --help`.
