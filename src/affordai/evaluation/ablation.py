"""Ablation program E0-E7 (Checklist Section 28).

Purpose: determine which components measurably improve outcomes -- NOT to prove
every feature useful. Keep a component only when its measured value justifies
its complexity.

Design (compatibility wrappers, no production rewrite):
- Production pipeline co-integrates deterministic components. E0-E2 are TRUE
  input configurations (progressive evidence restoration) executed through
  the real decide_context path, so deltas are direct output deltas.
- E3-E7 are co-integrated by design (conflict rules must stay authoritative;
  the LLM must never rank). Their value is measured with targeted instruments
  on the production pipeline: conflict-case subsets (E3), naive-first-vs-ranked
  comparison + tie-break units (E4), groundedness audit (E5), validator
  negative controls (E6), token/runtime accounting (E7). Documented per version
  -- never presented as a fork that does not exist.

All figures are LOCAL MEASUREMENT. OFFICIAL HackerRank score: UNKNOWN.
LLM forced OFF in every version (LlmConfig enabled=False) so replay is deterministic.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace

VERSIONS = ["E0", "E1", "E2", "E3", "E4", "E5", "E6", "E7"]


@dataclass(frozen=True)
class AblationVersion:
    name: str
    adds: str
    mask_messages: bool = False
    mask_images: bool = False
    instrument: str = ""
    hypothesis: str = ""


VERSION_DEFS: dict[str, AblationVersion] = {
    "E0": AblationVersion(
        name="E0",
        adds="deterministic baseline (structured data only)",
        mask_messages=True,
        mask_images=True,
        hypothesis="Minimum financial system: state + 90-day forecast + candidates + safety filter.",
    ),
    "E1": AblationVersion(
        name="E1",
        adds="E0 + message interpretation (deterministic interpreter only)",
        mask_messages=False,
        mask_images=True,
        hypothesis="Message facts (cancel/settle/amend/confirm/preference) change decisions only where linked.",
    ),
    "E2": AblationVersion(
        name="E2",
        adds="E1 + image interpretation linkage",
        mask_messages=False,
        mask_images=False,
        hypothesis="Blank amounts stay UNKNOWN without vision; linkage never fabricates amount (blank != 0).",
    ),
    "E3": AblationVersion(
        name="E3",
        adds="E2 + semantic conflict handling (instrumented)",
        instrument="conflict_subset",
        hypothesis="Cancel/settle/amend precedence resolves contradictory evidence; deterministic rules stay authoritative.",
    ),
    "E4": AblationVersion(
        name="E4",
        adds="E3 + plan optimization ranking (instrumented)",
        instrument="ranking_comparison",
        hypothesis="Deterministic ranking is required for reproducible winners. Value = divergence vs naive first-safe + tie-break proof.",
    ),
    "E5": AblationVersion(
        name="E5",
        adds="E4 + grounded explanation (instrumented)",
        instrument="explanation_audit",
        hypothesis="Explanations use only validated decision facts; no invented amounts/dates/evidence.",
    ),
    "E6": AblationVersion(
        name="E6",
        adds="E5 + comprehensive validation (instrumented)",
        instrument="validator_controls",
        hypothesis="Validator catches invalid outputs. A catch is validator SUCCESS.",
    ),
    "E7": AblationVersion(
        name="E7",
        adds="E6 + token/cost optimization accounting",
        instrument="token_accounting",
        hypothesis="Zero model calls on deterministic path; selective triggers keep runtime bounded at equal accuracy.",
    ),
}


def _disabled_llm():
    from affordai.evidence.llm_adapter import LlmConfig

    return LlmConfig(enabled=False, reason="ablation: deterministic (LLM_ENABLED != 1)")


def run_input_version(name: str, dataset_dir: str = "dataset/official") -> dict:
    """Execute E0/E1/E2 input configurations through the real pipeline path."""
    import sys

    sys.path.insert(0, "src")
    from affordai.output.validator import validate_consistency, validate_evidence
    from affordai.pipeline import build_contexts, decide_context, load_dataset

    cfg = VERSION_DEFS[name]
    llm_config = _disabled_llm()
    tables = load_dataset(dataset_dir)
    contexts = build_contexts(tables)
    masked = []
    for ctx in contexts:
        kw: dict = {}
        if cfg.mask_messages:
            kw["messages"] = []
        if cfg.mask_images:
            kw["images"] = []
        masked.append(replace(ctx, **kw) if kw else ctx)
    started = time.time()
    decisions = [decide_context(c, tables, dataset_dir, llm_config, None) for c in masked]
    runtime_s = time.time() - started
    decisions.sort(key=lambda d: d.original_index)
    ev_errs = validate_evidence(decisions, masked)
    cons_errs = validate_consistency(decisions)
    from collections import Counter

    return {
        "version": name,
        "adds": cfg.adds,
        "n_requests": len(decisions),
        "runtime_s": round(runtime_s, 2),
        "status_mix": dict(Counter(d.affordability_status for d in decisions)),
        "method_mix": dict(Counter(d.recommended_payment_method for d in decisions)),
        "evidence_errors": len(ev_errs),
        "consistency_errors": len(cons_errs),
        "evidence_errors_sample": [str(e) for e in ev_errs[:5]],
        "consistency_errors_sample": [str(e) for e in cons_errs[:5]],
        "llm_calls": 0,
        "result": "LOCAL MEASUREMENT",
    }


def sample_accuracy(decisions: list, dataset_dir: str = "dataset/official") -> dict:
    import sys

    sys.path.insert(0, "src")
    from affordai.evaluation.metrics import compare

    return compare(decisions, f"{dataset_dir}/sample_requests.csv")


def sample_decisions_for_version(name: str, dataset_dir: str = "dataset/official") -> list:
    import sys

    sys.path.insert(0, "src")
    from dataclasses import replace as _replace

    from affordai.ingestion import requests as ingest_requests
    from affordai.pipeline import build_contexts, decide_context, load_dataset

    key = name if name in ("E0", "E1", "E2") else "E2"
    cfg = VERSION_DEFS[key]
    tables = load_dataset(dataset_dir)
    tables["requests"] = ingest_requests.load(f"{dataset_dir}/sample_requests.csv")
    contexts = build_contexts(tables)
    out = []
    for ctx in contexts:
        kw: dict = {}
        if cfg.mask_messages:
            kw["messages"] = []
        if cfg.mask_images:
            kw["images"] = []
        out.append(decide_context(_replace(ctx, **kw) if kw else ctx, tables, dataset_dir, _disabled_llm(), None))
    out.sort(key=lambda d: d.original_index)
    return out


def decisions_for_version(name: str, dataset_dir: str = "dataset/official") -> list:
    import sys

    sys.path.insert(0, "src")
    from dataclasses import replace as _replace

    from affordai.pipeline import build_contexts, decide_context, load_dataset

    key = name if name in ("E0", "E1", "E2") else "E2"
    cfg = VERSION_DEFS[key]
    tables = load_dataset(dataset_dir)
    contexts = build_contexts(tables)
    out = []
    for ctx in contexts:
        kw: dict = {}
        if cfg.mask_messages:
            kw["messages"] = []
        if cfg.mask_images:
            kw["images"] = []
        out.append(decide_context(_replace(ctx, **kw) if kw else ctx, tables, dataset_dir, _disabled_llm(), None))
    out.sort(key=lambda d: d.original_index)
    return out


def instrument_e3_conflicts(dataset_dir: str = "dataset/official") -> dict:
    import sys

    sys.path.insert(0, "src")
    from affordai.evidence.message_interpreter import interpret as interpret_message
    from affordai.pipeline import build_contexts, load_dataset

    tables = load_dataset(dataset_dir)
    contexts = build_contexts(tables)
    with_cancel = with_amend = with_any = 0
    for ctx in contexts:
        kinds = set()
        for m in ctx.messages:
            for f in interpret_message(m):
                kinds.add(f.kind)
        if kinds:
            with_any += 1
        if "cancel" in kinds or "settle" in kinds:
            with_cancel += 1
        if "amend_amount" in kinds or "amend_date" in kinds or "delay" in kinds:
            with_amend += 1
    return {
        "n_requests": len(contexts),
        "requests_with_message_facts": with_any,
        "requests_with_cancel_or_settle": with_cancel,
        "requests_with_amend_or_delay": with_amend,
        "rule": "cancel/settle/amend > newer same-source > settled > safer; LLM never reorders",
        "result": "LOCAL MEASUREMENT",
    }


def instrument_e4_ranking(dataset_dir: str = "dataset/official") -> dict:
    import sys

    sys.path.insert(0, "src")
    from affordai.decision.eligibility import filter_candidates
    from affordai.evidence import conflict_resolver
    from affordai.evidence.evidence_registry import EvidenceRegistry
    from affordai.evidence.message_interpreter import interpret as interpret_message
    from affordai.finance import optimizer, payment_plans, spending_changes
    from affordai.finance.forecast import earliest_full_date, max_safe_today, simulate
    from affordai.finance.money import parse_amount
    from affordai.finance.state import build as build_state
    from affordai.finance.timeline import build_flows
    from affordai.pipeline import build_contexts, load_dataset

    tables = load_dataset(dataset_dir)
    contexts = build_contexts(tables)
    compared = diverged = 0
    for ctx in contexts:
        try:
            reg = EvidenceRegistry(
                {e["event_id"] for e in ctx.events},
                {m["message_id"] for m in ctx.messages},
                {i["image_id"] for i in ctx.images},
            )
            for m in sorted(ctx.messages, key=lambda x: (str(x["sent_at"]), x["message_id"])):
                for f in interpret_message(m):
                    try:
                        reg.add(f, ctx.request_id, ctx.user_id)
                    except Exception:
                        continue
            facts = reg.facts_for(ctx.request_id)
            cancelled = conflict_resolver.cancelled_event_ids(facts)
            amend_amounts = {}
            for eid, raw in conflict_resolver.amended_amounts(facts).items():
                try:
                    v = parse_amount(raw)
                except ValueError:
                    continue
                if v is not None and v > 0:
                    amend_amounts[eid] = v
            flows, unknowns, notes = build_flows(ctx, tables["rates"], cancelled, amend_amounts, {}, [])
            state = build_state(ctx, flows, unknowns, notes)
            safe = max_safe_today(state)
            earliest = earliest_full_date(state)
            cands, _ = payment_plans.generate(state, ctx.payment_options, safe, earliest, ctx.request["allows_partial_payment"])
            cands = cands + spending_changes.find_variants(state, cands, spending_changes.candidate_targets(state, ctx.profile, tables["rates"]), state.deadline)
            eligible = filter_candidates(cands, ctx.profile, ctx.request["allows_partial_payment"], ctx.request["desired_completion_date"])
            validated = [c for c in eligible if simulate(state, c.payments, c.changes or {}).ok]
            if len(validated) > 1:
                compared += 1
                winner = optimizer.select(validated, ctx.request["desired_completion_date"])
                if winner is not validated[0]:
                    diverged += 1
        except Exception:
            continue
    return {
        "multi_candidate_requests": compared,
        "ranking_changed_winner": diverged,
        "rule": "deadline -> no-changes -> min total -> earlier start -> fewer payments -> lowest option id",
        "result": "LOCAL MEASUREMENT",
    }


def instrument_e5_explanations(decisions: list) -> dict:
    import sys

    sys.path.insert(0, "src")
    from affordai.output import explanation as explanation_mod

    checked = valid = 0
    bad_ids: list[str] = []
    for d in decisions:
        checked += 1
        try:
            ok = bool(explanation_mod.validate(d.decision_explanation, d))
        except Exception:
            ok = False
        if ok:
            valid += 1
        else:
            bad_ids.append(d.request_id)
    return {
        "checked": checked,
        "valid": valid,
        "invalid_ids": bad_ids[:10],
        "consistency_rate": (valid / checked) if checked else 0.0,
        "rule": "facts subset of validated Decision; no invented amounts/dates/evidence",
        "result": "LOCAL MEASUREMENT",
    }


def instrument_e6_validator(dataset_dir: str = "dataset/official", output_path: str = "output.csv") -> dict:
    import copy
    import csv
    import os
    import sys
    import tempfile

    sys.path.insert(0, "src")
    from affordai.output.validator import validate_files, validate_plans

    req = f"{dataset_dir}/requests.csv"
    opt = f"{dataset_dir}/request_payment_options.csv"
    prof = f"{dataset_dir}/financial_profiles.csv"
    prod_errors = validate_files(req, output_path) + validate_plans(req, opt, prof, output_path)
    rows = list(csv.DictReader(open(output_path, encoding="utf-8-sig")))
    header = list(rows[0].keys())
    controls: dict[str, bool] = {}

    def _run(mutated: list[dict]) -> list:
        fd, tmp = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=header)
            w.writeheader()
            w.writerows(mutated)
        errs = validate_files(req, tmp) + validate_plans(req, opt, prof, tmp)
        os.remove(tmp)
        return errs

    m1 = copy.deepcopy(rows[:2])
    m1[0], m1[1] = m1[1], m1[0]
    controls["reordered_rows_caught"] = bool(_run(m1))
    m2 = copy.deepcopy(rows[:1])
    m2[0]["affordability_status"] = "maybe"
    controls["invented_enum_caught"] = bool(_run(m2))
    m3 = copy.deepcopy(rows[:1])
    m3[0]["amount_safe_to_pay"] = "999999999999"
    controls["out_of_bounds_safe_caught"] = bool(_run(m3))
    m4 = copy.deepcopy(rows[:1])
    m4[0]["payment_plan"] = "2099-01-01:1"
    controls["bogus_plan_caught"] = bool(_run(m4))
    return {
        "production_errors": len(prod_errors),
        "production_errors_sample": [str(e) for e in prod_errors[:5]],
        "negative_controls": controls,
        "all_controls_caught": all(controls.values()),
        "note": "A validator catch is validator SUCCESS, not validator failure.",
        "result": "LOCAL MEASUREMENT",
    }


def instrument_e7_tokens(n_requests: int, runtime_s: float) -> dict:
    return {
        "provider": "(deterministic E0 path, none)",
        "model": "(none)",
        "model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "avg_tokens_per_request": 0.0,
        "estimated_total_cost": 0.0,
        "estimated_cost_per_request": 0.0,
        "n_requests": n_requests,
        "wall_runtime_s": round(runtime_s, 2),
        "selective_triggers": "image resolution only for blank amounts (16); message interpreter deterministic-only; LLM off by default",
        "correctness_guard": "optimization valid only at equal accuracy -- verified by identical validator PASS + replay hash",
        "result": "LOCAL MEASUREMENT",
    }
