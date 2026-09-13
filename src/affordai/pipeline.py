"""AffordAI pipeline orchestrator (deterministic E0).

load -> validate -> normalize -> resolve evidence -> financial state ->
forecast -> candidates -> validate candidates -> rank -> Decision ->
serialize -> validate output -> evaluate.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal

from affordai.decision import rules as decision_rules
from affordai.decision.decision import Decision
from affordai.decision.eligibility import filter_candidates
from affordai.evidence import conflict_resolver
from affordai.evidence.evidence_registry import EvidenceRegistry
from affordai.evidence.image_interpreter import (
    amount_unknown_evidence,
    resolve_images_for_event,
)
from affordai.evidence.llm_adapter import (
    LlmConfig,
    load_config_from_env,
    propose_facts,
)
from affordai.evidence.message_interpreter import interpret as interpret_message
from affordai.finance import optimizer, payment_plans, spending_changes
from affordai.finance.currency import load_rates
from affordai.finance.forecast import earliest_full_date, max_safe_today, simulate
from affordai.finance.money import format_amount, parse_amount
from affordai.finance.state import build as build_state
from affordai.finance.timeline import build_flows
from affordai.ingestion import events as ingest_events
from affordai.ingestion import images as ingest_images
from affordai.ingestion import messages as ingest_messages
from affordai.ingestion import payment_options as ingest_options
from affordai.ingestion import profiles as ingest_profiles
from affordai.ingestion import requests as ingest_requests
from affordai.observability.tracing import Trace
from affordai.output import explanation as explanation_mod


@dataclass
class RequestContext:
    original_index: int
    request_id: str
    user_id: str
    request: dict
    profile: dict
    events: list
    messages: list
    images: list
    payment_options: list
    evidence: list = field(default_factory=list)


def _resolve_dataset_path(dataset_dir: str, filename: str) -> str:
    """Support both upstream `dataset/` and local `dataset/official/` layouts."""
    direct = os.path.join(dataset_dir, filename)
    if os.path.exists(direct):
        return direct
    nested = os.path.join(dataset_dir, "official", filename)
    if os.path.exists(nested):
        return nested
    # If dataset_dir itself is already .../official but caller passed parent,
    # also try stripping official
    if dataset_dir.endswith("official"):
        parent = os.path.dirname(dataset_dir)
        alt = os.path.join(parent, filename)
        if os.path.exists(alt):
            return alt
    return direct  # let loader raise clear DatasetError


def load_dataset(dataset_dir: str) -> dict:
    j = lambda *p: _resolve_dataset_path(dataset_dir, os.path.join(*p))
    requests = ingest_requests.load(j("requests.csv"))
    tables = {
        "requests": requests,
        "profiles": ingest_profiles.load(j("financial_profiles.csv")),
        "events": ingest_events.load(j("financial_events.csv")),
        "options": ingest_options.load(j("request_payment_options.csv")),
        "messages": ingest_messages.load_messages(j("messages.csv")),
        "images": ingest_images.load(j("images.csv")),
        "rates": load_rates(j("exchange_rates.csv")),
    }
    return tables


def build_contexts(tables: dict) -> list[RequestContext]:
    by_user_events: dict[str, list] = {}
    for e in tables["events"]:
        by_user_events.setdefault(e["user_id"], []).append(e)
    by_request_options: dict[str, list] = {}
    for o in tables["options"]:
        by_request_options.setdefault(o["request_id"], []).append(o)
    contexts = []
    for req in tables["requests"]:
        uid = req["user_id"]
        rid = req["request_id"]
        messages = [
            m
            for m in tables["messages"]
            if m["request_id"] == rid
            or (m["request_id"] is None and m["user_id"] == uid)
        ]
        images = [
            i
            for i in tables["images"]
            if i["request_id"] == rid
            or (i["request_id"] is None and i["user_id"] == uid)
        ]
        contexts.append(
            RequestContext(
                original_index=req["original_index"],
                request_id=rid,
                user_id=uid,
                request=req,
                profile=tables["profiles"][uid],
                events=by_user_events.get(uid, []),
                messages=messages,
                images=images,
                payment_options=sorted(
                    by_request_options.get(rid, []),
                    key=lambda o: o["payment_option_id"],
                ),
            )
        )
    return contexts


def _link_salary_fact(ctx: RequestContext, message: dict, fact) -> None:
    """Link request-level payroll amounts to the earliest scheduled salary."""
    from affordai.evidence.message_interpreter import SALARY_RE

    text = message.get("message_text") or ""
    if not SALARY_RE.search(text):
        return
    req_date = ctx.request["request_date"]
    candidates = sorted(
        (
            e
            for e in ctx.events
            if e["status"] == "scheduled"
            and (e["event_type"] == "income" or e["category"] == "salary")
            and e["settlement_date"] >= req_date
        ),
        key=lambda e: e["settlement_date"],
    )
    if candidates:
        fact.event_id = candidates[0]["event_id"]


def _collect_evidence(
    ctx: RequestContext,
    media_dir: str,
    llm_config: LlmConfig,
    trace: Trace | None,
) -> tuple[EvidenceRegistry, list[str]]:
    """Deterministic evidence + optional LLM proposals (validated or dropped)."""
    registry = EvidenceRegistry()
    used: list[str] = []
    for message in sorted(ctx.messages, key=lambda m: (str(m["sent_at"]), m["message_id"])):
        for fact in interpret_message(message):
            if fact.kind == "amend_amount" and not fact.event_id:
                _link_salary_fact(ctx, message, fact)
            try:
                registry.add(fact, ctx.request_id, ctx.user_id)
                used.append(fact.source_id)
            except Exception:
                continue
    llm = propose_facts(
        "message",
        {"request_id": ctx.request_id, "n_messages": len(ctx.messages)},
        llm_config,
    )
    for fact in llm.facts:
        if fact.confidence < llm_config.min_confidence:
            continue
        try:
            registry.add(fact, ctx.request_id, ctx.user_id)
            used.append(fact.source_id)
        except Exception:
            continue
    # Blank-amount linkage: resolve images; amounts stay UNKNOWN without vision.
    for event in ctx.events:
        if event["amount"] is not None:
            continue
        linked = resolve_images_for_event(
            event["event_id"], ctx.images, media_dir
        )
        img_proposals = propose_facts(
            "image_amount",
            {
                "event_id": event["event_id"],
                "images": [d["image_id"] for d in linked if d["file_exists"]],
            },
            llm_config,
        )
        filled = False
        for fact in img_proposals.facts:
            if fact.confidence < llm_config.min_confidence:
                continue
            try:
                value = parse_amount(fact.normalized_value)
            except ValueError:
                continue
            if value is None or value <= 0:
                continue
            event["amount"] = value
            filled = True
            try:
                registry.add(fact, ctx.request_id, ctx.user_id)
                used.append(fact.source_id)
            except Exception:
                pass
            break
        if not filled:
            image_id = linked[0]["image_id"] if linked else None
            registry.add(
                amount_unknown_evidence(
                    event["event_id"], image_id, ctx.request_id, ctx.user_id
                ),
                ctx.request_id,
                ctx.user_id,
            )
    if trace is not None:
        trace.record(
            "evidence",
            ctx.request_id,
            f"{len(registry)} facts, llm_fallback={llm.fallback_reason}",
        )
    return registry, used


def decide_context(
    ctx: RequestContext,
    tables: dict,
    dataset_dir: str,
    llm_config: LlmConfig | None = None,
    trace: Trace | None = None,
) -> Decision:
    llm_config = llm_config or LlmConfig()
    media_dir = os.path.join(dataset_dir, "media", "images")
    home = ctx.profile["home_currency"]
    req = ctx.request
    requested = req["requested_amount"]
    req_date = req["request_date"]

    registry, _used = _collect_evidence(ctx, media_dir, llm_config, trace)
    facts = registry.facts_for(ctx.request_id)
    cancelled = conflict_resolver.cancelled_event_ids(facts)
    # Message-confirmed salary: narrow deterministic E1 (employer confirms).
    from affordai.evidence.message_income import confirmed_series

    extra_confirmed: list[tuple] = []
    for message in sorted(ctx.messages, key=lambda m: (str(m["sent_at"]), m["message_id"])):
        try:
            series, _income_notes = confirmed_series(ctx, message, home)
        except Exception:
            continue
        for day, amount in series:
            extra_confirmed.append((day, amount, message["message_id"]))
    amend_raw = conflict_resolver.amended_amounts(facts)
    amend_amounts: dict[str, Decimal] = {}
    for eid, raw in amend_raw.items():
        try:
            value = parse_amount(raw)
        except ValueError:
            continue
        if value is not None and value > 0:
            amend_amounts[eid] = value
    amend_dates = {}
    for eid, raw in conflict_resolver.amended_dates(facts).items():
        try:
            from datetime import datetime as _dt

            amend_dates[eid] = _dt.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            continue

    flows, unknowns, notes = build_flows(
        ctx, tables["rates"], cancelled, amend_amounts, amend_dates, extra_confirmed
    )
    state = build_state(ctx, flows, unknowns, notes)

    safe = max_safe_today(state)
    earliest = earliest_full_date(state)

    candidates, gen_notes = payment_plans.generate(
        state, ctx.payment_options, safe, earliest, req["allows_partial_payment"]
    )
    targets = spending_changes.candidate_targets(state, ctx.profile)
    candidates = candidates + spending_changes.find_variants(state, candidates, targets)
    eligible = filter_candidates(
        candidates, ctx.profile, req["allows_partial_payment"], req["desired_completion_date"]
    )
    validated = [
        c for c in eligible if simulate(state, c.payments, c.changes or {}).ok
    ]
    winner = optimizer.select(validated, req["desired_completion_date"]) if validated else None
    status, method = decision_rules.derive(winner)

    if winner is None:
        plan: object = "none"
        changes: object = "none"
    else:
        from affordai.output.serializer import format_changes, format_plan

        plan = format_plan(winner.payments, home)
        changes = format_changes(winner.changes or {}, home)

    decision = Decision(
        original_index=ctx.original_index,
        request_id=ctx.request_id,
        user_id=ctx.user_id,
        amount_safe_to_pay=safe,
        affordability_status=status,
        recommended_payment_method=method,
        payment_plan=plan,
        earliest_date_for_full_payment=earliest.isoformat() if earliest else "",
        spending_changes_needed=changes,
        decision_explanation="",
        evidence=sorted(
            {
                f.source_id
                for f in facts
                if f.kind in ("cancel", "amend_amount", "amend_date", "amount")
                and f.event_id
            }
        ),
    )
    decision.decision_explanation = explanation_mod.build(
        decision, format_amount(requested, home), req_date.isoformat(), home
    )
    if trace is not None:
        trace.record(
            "decision",
            ctx.request_id,
            f"{status}/{method} safe={safe} earliest={earliest} "
            f"candidates={len(candidates)} eligible={len(eligible)} "
            f"notes={';'.join(notes + gen_notes)[:200]}",
        )
    return decision


def _fallback_decision(ctx: RequestContext, reason: str) -> Decision:
    """Safest valid decision when a request cannot be processed: never crash."""
    return Decision(
        original_index=ctx.original_index,
        request_id=ctx.request_id,
        user_id=ctx.user_id,
        amount_safe_to_pay=Decimal("0"),
        affordability_status="not_affordable",
        recommended_payment_method="not_recommended",
        payment_plan="none",
        earliest_date_for_full_payment="",
        spending_changes_needed="none",
        decision_explanation=(
            f"Processing failure ({reason}); safest fallback applied, "
            "no payment recommended."
        ),
        evidence=[],
    )


def _decide_safe(
    ctx: RequestContext,
    tables: dict,
    dataset_dir: str,
    llm_config: LlmConfig,
    trace: Trace | None,
) -> tuple[Decision, bool]:
    """Decide one request; on unexpected failure return the safe fallback."""
    try:
        return decide_context(ctx, tables, dataset_dir, llm_config, trace), False
    except Exception as exc:  # never crash the batch; degrade to safest valid row
        if trace is not None:
            trace.record("decision-fallback", ctx.request_id, f"{type(exc).__name__}: {exc}"[:200])
        return _fallback_decision(ctx, type(exc).__name__), True


def run(
    dataset_dir: str,
    llm_config: LlmConfig | None = None,
    trace: Trace | None = None,
) -> tuple[list[Decision], dict]:
    """Run the full deterministic pipeline. Returns (decisions, usage)."""
    from affordai.evaluation.usage import UsageReport

    llm_config = llm_config or load_config_from_env()
    tables = load_dataset(dataset_dir)
    contexts = build_contexts(tables)
    decisions: list[Decision] = []
    fallbacks = 0
    for ctx in contexts:
        decision, failed = _decide_safe(ctx, tables, dataset_dir, llm_config, trace)
        decisions.append(decision)
        fallbacks += failed
    decisions.sort(key=lambda d: d.original_index)
    usage = UsageReport(
        provider=llm_config.provider,
        model=llm_config.model,
        calls=0,
        input_tokens=0,
        output_tokens=0,
        note=f"deterministic E0 (llm: {llm_config.reason})",
    )
    return decisions, {
        "usage": usage,
        "n_requests": len(decisions),
        "n_fallbacks": fallbacks,
        "llm_reason": llm_config.reason,
    }
