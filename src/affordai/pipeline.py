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
class JoinIntegrityIssue:
    """Structured integrity issue for join/validation failures (never silently dropped)."""

    code: str  # MISSING_REFERENCE | WRONG_USER | WRONG_REQUEST | DUPLICATE_JOIN | ORPHAN
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    request_id: str
    user_id: str
    reason: str
    severity: str = "warning"  # warning | error


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
    join_issues: list = field(default_factory=list)  # JoinIntegrityIssue[]

    def validate_identity(self) -> list[str]:
        """Validate immutable identity fields."""
        errors: list[str] = []
        if not isinstance(self.original_index, int) or self.original_index < 0:
            errors.append(f"invalid original_index {self.original_index!r}")
        if not self.request_id or not str(self.request_id).strip():
            errors.append("missing request_id")
        if not self.user_id or not str(self.user_id).strip():
            errors.append("missing user_id")
        # Ensure stored IDs match request/profile
        if self.request.get("request_id") != self.request_id:
            errors.append(f"request_id mismatch {self.request.get('request_id')} != {self.request_id}")
        if self.request.get("user_id") != self.user_id:
            errors.append(f"user_id mismatch {self.request.get('user_id')} != {self.user_id}")
        if self.profile.get("user_id") != self.user_id:
            errors.append(f"profile user_id mismatch {self.profile.get('user_id')} != {self.user_id}")
        return errors

    def validate_relationships(self) -> list[JoinIntegrityIssue]:
        """Return join integrity issues (wrong-user/wrong-request/duplicate/orphan)."""
        issues: list[JoinIntegrityIssue] = []
        # Return already-collected issues plus live checks
        issues.extend(self.join_issues)
        # Cross-check event ownership
        for e in self.events:
            if e.get("user_id") != self.user_id:
                issues.append(
                    JoinIntegrityIssue(
                        code="WRONG_USER",
                        source_type="event",
                        source_id=e.get("event_id", "?"),
                        target_type="context",
                        target_id=self.request_id,
                        request_id=self.request_id,
                        user_id=self.user_id,
                        reason=f"event {e.get('event_id')} belongs to {e.get('user_id')}, not {self.user_id}",
                        severity="error",
                    )
                )
        for m in self.messages:
            if m.get("user_id") != self.user_id:
                issues.append(
                    JoinIntegrityIssue(
                        code="WRONG_USER",
                        source_type="message",
                        source_id=m.get("message_id", "?"),
                        target_type="context",
                        target_id=self.request_id,
                        request_id=self.request_id,
                        user_id=self.user_id,
                        reason=f"message {m.get('message_id')} belongs to user {m.get('user_id')}",
                        severity="error",
                    )
                )
            if m.get("request_id") is not None and m["request_id"] != self.request_id:
                issues.append(
                    JoinIntegrityIssue(
                        code="WRONG_REQUEST",
                        source_type="message",
                        source_id=m.get("message_id", "?"),
                        target_type="context",
                        target_id=self.request_id,
                        request_id=self.request_id,
                        user_id=self.user_id,
                        reason=f"message {m.get('message_id')} belongs to request {m.get('request_id')}",
                        severity="error",
                    )
                )
        for img in self.images:
            if img.get("user_id") != self.user_id:
                issues.append(
                    JoinIntegrityIssue(
                        code="WRONG_USER",
                        source_type="image",
                        source_id=img.get("image_id", "?"),
                        target_type="context",
                        target_id=self.request_id,
                        request_id=self.request_id,
                        user_id=self.user_id,
                        reason=f"image {img.get('image_id')} belongs to user {img.get('user_id')}",
                        severity="error",
                    )
                )
            if img.get("request_id") is not None and img["request_id"] != self.request_id:
                issues.append(
                    JoinIntegrityIssue(
                        code="WRONG_REQUEST",
                        source_type="image",
                        source_id=img.get("image_id", "?"),
                        target_type="context",
                        target_id=self.request_id,
                        request_id=self.request_id,
                        user_id=self.user_id,
                        reason=f"image {img.get('image_id')} belongs to request {img.get('request_id')}",
                        severity="error",
                    )
                )
        return issues


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


def _dedupe_by_key(rows: list[dict], key: str) -> tuple[list[dict], list[JoinIntegrityIssue]]:
    """Deduplicate by identity key; record duplicates as integrity issues (no content blind collapse)."""
    seen: dict[str, dict] = {}
    deduped: list[dict] = []
    issues: list[JoinIntegrityIssue] = []
    for r in rows:
        kid = r.get(key, "")
        if kid in seen:
            issues.append(
                JoinIntegrityIssue(
                    code="DUPLICATE_JOIN",
                    source_type=key,
                    source_id=str(kid),
                    target_type="context",
                    target_id="",
                    request_id="",
                    user_id="",
                    reason=f"duplicate {key} {kid} deduplicated (kept first)",
                    severity="warning",
                )
            )
            continue
        seen[kid] = r
        deduped.append(r)
    return deduped, issues


def build_contexts(tables: dict) -> list[RequestContext]:
    """Build canonical contexts with join safety guarantees.

    - original_index/request_id/user_id immutable and sourced from requests.
    - Deterministic ordering: events sorted by (settlement_date, event_id),
      messages by (sent_at, message_id), images by image_id, options by payment_option_id.
    - Ownership enforcement: messages/images must satisfy user_id == ctx.user_id;
      request-bound records must also satisfy request_id == ctx.request_id.
    - Dedup by PK, preserve one-to-many, never blind collapse.
    - Isolation: each context gets shallow-copied list/dict so alias mutation cannot leak.
    - Missing refs recorded as JoinIntegrityIssue, not silently discarded.
    """
    import copy as _copy

    # Validate request identity upfront
    _validate_request_identity(tables["requests"])

    # Validate FK integrity and collect orphan issues (reported, not fabricated)
    fk_issues = _validate_fk_integrity(tables)

    by_user_events: dict[str, list] = {}
    for e in tables["events"]:
        by_user_events.setdefault(e["user_id"], []).append(e)
    by_request_options: dict[str, list] = {}
    for o in tables["options"]:
        by_request_options.setdefault(o["request_id"], []).append(o)

    # Per-user issues index for quick attachment
    issues_by_user: dict[str, list[JoinIntegrityIssue]] = {}
    issues_by_request: dict[str, list[JoinIntegrityIssue]] = {}
    for iss in fk_issues:
        if iss.user_id:
            issues_by_user.setdefault(iss.user_id, []).append(iss)
        if iss.request_id:
            issues_by_request.setdefault(iss.request_id, []).append(iss)

    contexts: list[RequestContext] = []
    for req in tables["requests"]:
        uid = req["user_id"]
        rid = req["request_id"]

        # Messages: must belong to this user; if request-bound, must match rid
        raw_messages = [
            m
            for m in tables["messages"]
            if m.get("user_id") == uid and (m.get("request_id") in (rid, None))
        ]
        # Images: same ownership rule
        raw_images = [
            i
            for i in tables["images"]
            if i.get("user_id") == uid and (i.get("request_id") in (rid, None))
        ]
        # Record wrong-user attempts that were rejected (for observability)
        rejected_messages = [
            m for m in tables["messages"] if m.get("request_id") == rid and m.get("user_id") != uid
        ]
        rejected_images = [
            i for i in tables["images"] if i.get("request_id") == rid and i.get("user_id") != uid
        ]

        # Deduplicate by PK (preserve one-to-many correctly)
        deduped_events, dup_e_issues = _dedupe_by_key(by_user_events.get(uid, []), "event_id")
        deduped_messages, dup_m_issues = _dedupe_by_key(raw_messages, "message_id")
        deduped_images, dup_i_issues = _dedupe_by_key(raw_images, "image_id")
        deduped_options, dup_o_issues = _dedupe_by_key(by_request_options.get(rid, []), "payment_option_id")

        # Deterministic ordering (official ordering semantics where specified; else stable PK)
        deduped_events = sorted(deduped_events, key=lambda e: (str(e.get("settlement_date")), e.get("event_id", "")))
        deduped_messages = sorted(deduped_messages, key=lambda m: (str(m.get("sent_at")), m.get("message_id", "")))
        deduped_images = sorted(deduped_images, key=lambda i: i.get("image_id", ""))
        deduped_options = sorted(deduped_options, key=lambda o: o.get("payment_option_id", ""))

        # Isolation: shallow copy lists and request/profile dicts so mutation cannot leak
        req_copy = dict(req)
        prof_raw = tables["profiles"].get(uid)
        if prof_raw is None:
            # Record missing reference instead of KeyError; fallback will handle
            raise KeyError(f"profile missing for user {uid} (request {rid})")
        prof_copy = dict(prof_raw)
        # Shallow copy events/messages/images so callers can mutate amount without leaking
        events_copy = [dict(e) for e in deduped_events]
        messages_copy = [dict(m) for m in deduped_messages]
        images_copy = [dict(i) for i in deduped_images]
        options_copy = [dict(o) for o in deduped_options]

        join_issues: list[JoinIntegrityIssue] = []
        join_issues.extend(dup_e_issues)
        join_issues.extend(dup_m_issues)
        join_issues.extend(dup_i_issues)
        join_issues.extend(dup_o_issues)
        # Attach FK-level issues for this context
        join_issues.extend(issues_by_user.get(uid, []))
        join_issues.extend(issues_by_request.get(rid, []))
        for m in rejected_messages:
            join_issues.append(
                JoinIntegrityIssue(
                    code="WRONG_USER",
                    source_type="message",
                    source_id=m.get("message_id", "?"),
                    target_type="context",
                    target_id=rid,
                    request_id=rid,
                    user_id=uid,
                    reason=f"rejected: message {m.get('message_id')} belongs to user {m.get('user_id')}, not {uid}",
                    severity="warning",
                )
            )
        for img in rejected_images:
            join_issues.append(
                JoinIntegrityIssue(
                    code="WRONG_USER",
                    source_type="image",
                    source_id=img.get("image_id", "?"),
                    target_type="context",
                    target_id=rid,
                    request_id=rid,
                    user_id=uid,
                    reason=f"rejected: image {img.get('image_id')} belongs to user {img.get('user_id')}",
                    severity="warning",
                )
            )
        # Orphan related_event_id check (message/image points to non-existent event)
        event_ids = {e.get("event_id") for e in deduped_events}
        for m in deduped_messages:
            rel = m.get("related_event_id")
            if rel and rel not in event_ids:
                # Only flag if global event exists but not in this user's context -> wrong-user leak attempt already blocked
                # If truly missing globally, record orphan
                join_issues.append(
                    JoinIntegrityIssue(
                        code="MISSING_REFERENCE",
                        source_type="message",
                        source_id=m.get("message_id", "?"),
                        target_type="event",
                        target_id=str(rel),
                        request_id=rid,
                        user_id=uid,
                        reason=f"related_event_id {rel} not found in user {uid} events (orphan, evidence unusable)",
                        severity="warning",
                    )
                )

        contexts.append(
            RequestContext(
                original_index=req["original_index"],
                request_id=rid,
                user_id=uid,
                request=req_copy,
                profile=prof_copy,
                events=events_copy,
                messages=messages_copy,
                images=images_copy,
                payment_options=options_copy,
                join_issues=join_issues,
            )
        )
    return contexts


def _validate_request_identity(requests: list[dict]) -> None:
    seen_idx: set[int] = set()
    seen_req: set[str] = set()
    for r in requests:
        idx = r.get("original_index")
        rid = r.get("request_id")
        uid = r.get("user_id")
        if idx is None:
            raise ValueError(f"missing original_index for request {rid}")
        if idx in seen_idx:
            raise ValueError(f"duplicate original_index {idx} (request {rid})")
        seen_idx.add(idx)
        if not rid or not str(rid).strip():
            raise ValueError(f"missing request_id at index {idx}")
        if rid in seen_req:
            raise ValueError(f"duplicate request_id {rid}")
        seen_req.add(rid)
        if not uid or not str(uid).strip():
            raise ValueError(f"missing user_id for request {rid}")


def _validate_fk_integrity(tables: dict) -> list[JoinIntegrityIssue]:
    """Collect FK/orphan issues across tables; return issues without mutating tables."""
    issues: list[JoinIntegrityIssue] = []
    profile_users = set(tables["profiles"].keys())
    request_ids = {r["request_id"] for r in tables["requests"]}
    event_ids = {e["event_id"] for e in tables["events"]}
    # requests.user_id -> profiles
    for r in tables["requests"]:
        if r["user_id"] not in profile_users:
            issues.append(
                JoinIntegrityIssue(
                    code="MISSING_REFERENCE",
                    source_type="request",
                    source_id=r["request_id"],
                    target_type="profile",
                    target_id=r["user_id"],
                    request_id=r["request_id"],
                    user_id=r["user_id"],
                    reason=f"profile missing for user {r['user_id']}",
                    severity="error",
                )
            )
    # events.user_id -> profiles, linked_event_id -> events
    for e in tables["events"]:
        if e["user_id"] not in profile_users:
            issues.append(
                JoinIntegrityIssue(
                    code="MISSING_REFERENCE",
                    source_type="event",
                    source_id=e["event_id"],
                    target_type="profile",
                    target_id=e["user_id"],
                    request_id="",
                    user_id=e["user_id"],
                    reason=f"event {e['event_id']} user {e['user_id']} not in profiles",
                    severity="warning",
                )
            )
        lid = e.get("linked_event_id")
        if lid and lid not in event_ids:
            issues.append(
                JoinIntegrityIssue(
                    code="MISSING_REFERENCE",
                    source_type="event",
                    source_id=e["event_id"],
                    target_type="event",
                    target_id=str(lid),
                    request_id="",
                    user_id=e["user_id"],
                    reason=f"linked_event_id {lid} not found",
                    severity="warning",
                )
            )
    # options.request_id -> requests, messages.request_id -> requests, images similar (allow None)
    # Partition-aware: caller may supply tables["_sample_ids"] (sample_requests ids);
    # otherwise only eval request_ids are valid. No filesystem probing here
    # (keeps validator pure + deterministic; layout handling lives in _resolve_dataset_path).
    sample_ids: set[str] = set(tables.get("_sample_ids") or set())
    valid_requests = request_ids | sample_ids
    for o in tables["options"]:
        if o["request_id"] not in valid_requests:
            issues.append(
                JoinIntegrityIssue(
                    code="MISSING_REFERENCE",
                    source_type="payment_option",
                    source_id=o["payment_option_id"],
                    target_type="request",
                    target_id=o["request_id"],
                    request_id=o["request_id"],
                    user_id="",
                    reason=f"option {o['payment_option_id']} request {o['request_id']} not in requests",
                    severity="warning",
                )
            )
    for m in tables["messages"]:
        rid = m.get("request_id")
        if rid and rid not in valid_requests:
            issues.append(
                JoinIntegrityIssue(
                    code="MISSING_REFERENCE",
                    source_type="message",
                    source_id=m["message_id"],
                    target_type="request",
                    target_id=str(rid),
                    request_id=str(rid),
                    user_id=m.get("user_id", ""),
                    reason=f"message {m['message_id']} request_id {rid} not found",
                    severity="warning",
                )
            )
        rel = m.get("related_event_id")
        if rel and rel not in event_ids:
            issues.append(
                JoinIntegrityIssue(
                    code="MISSING_REFERENCE",
                    source_type="message",
                    source_id=m["message_id"],
                    target_type="event",
                    target_id=str(rel),
                    request_id=str(m.get("request_id") or ""),
                    user_id=m.get("user_id", ""),
                    reason=f"related_event_id {rel} not found",
                    severity="warning",
                )
            )
    for img in tables["images"]:
        rid = img.get("request_id")
        if rid and rid not in valid_requests:
            issues.append(
                JoinIntegrityIssue(
                    code="MISSING_REFERENCE",
                    source_type="image",
                    source_id=img["image_id"],
                    target_type="request",
                    target_id=str(rid),
                    request_id=str(rid),
                    user_id=img.get("user_id", ""),
                    reason=f"image {img['image_id']} request_id {rid} not found",
                    severity="warning",
                )
            )
        rel = img.get("related_event_id")
        if rel and rel not in event_ids:
            issues.append(
                JoinIntegrityIssue(
                    code="MISSING_REFERENCE",
                    source_type="image",
                    source_id=img["image_id"],
                    target_type="event",
                    target_id=str(rel),
                    request_id=str(img.get("request_id") or ""),
                    user_id=img.get("user_id", ""),
                    reason=f"related_event_id {rel} not found",
                    severity="warning",
                )
            )
    return issues


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
    valid_event_ids = {e["event_id"] for e in ctx.events}
    valid_message_ids = {m["message_id"] for m in ctx.messages}
    valid_image_ids = {i["image_id"] for i in ctx.images}
    registry = EvidenceRegistry(valid_event_ids, valid_message_ids, valid_image_ids)
    used: list[str] = []
    for message in sorted(ctx.messages, key=lambda m: (str(m["sent_at"]), m["message_id"])):
        for fact in interpret_message(message):
            if fact.kind == "amend_amount" and not fact.event_id:
                _link_salary_fact(ctx, message, fact)
            # Stamp sent_at for Rule 2 conflict resolution
            fact.sent_at = str(message.get("sent_at") or "")
            # Ensure provenance completeness: fill message_id if missing
            if not fact.message_id:
                fact.message_id = message["message_id"]
            # Preserve extraction method
            fact.extraction_method = fact.method
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
        # Validate LLM provenance: ensure it carries required fields
        if not fact.source_type or not fact.source_id:
            continue
        fact.extraction_method = fact.method
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
            # Zero-trust: image path may only emit amount facts; any other kind (e.g. injected cancel) is dropped
            if fact.kind != "amount":
                continue
            if fact.confidence < llm_config.min_confidence:
                continue
            try:
                value = parse_amount(fact.normalized_value)
            except ValueError:
                continue
            if value is None or value <= 0:
                continue
            fact.extraction_method = fact.method
            # Preserve raw vs normalized: raw already captured, normalized validated
            if not fact.raw_value:
                fact.raw_value = str(fact.normalized_value)
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
            unknown_fact = amount_unknown_evidence(
                event["event_id"], image_id, ctx.request_id, ctx.user_id
            )
            unknown_fact.extraction_method = unknown_fact.method
            registry.add(
                unknown_fact,
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
                if f.kind in ("cancel", "settle", "amend_amount", "amend_date", "delay", "confirm", "amount", "preference")
                and (f.event_id or f.kind in ("preference", "confirm", "settle"))
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
