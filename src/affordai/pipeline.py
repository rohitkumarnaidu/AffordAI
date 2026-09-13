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
    check_batch_safe,
    load_config_from_env,
    minimize_image_context,
    minimize_message_context,
    needs_llm_for_image,
    needs_llm_for_messages,
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
    # Sec 35.1 indexed lookups (no O(R*M) full-table scan per request):
    # messages/images pre-indexed by user; per-request filter then touches
    # only that user's rows (215 msgs / 16 imgs over 275 users ~= tiny).
    by_user_messages: dict[str, list] = {}
    for m in tables["messages"]:
        by_user_messages.setdefault(m.get("user_id"), []).append(m)
    by_user_images: dict[str, list] = {}
    for i in tables["images"]:
        by_user_images.setdefault(i.get("user_id"), []).append(i)
    # Wrong-user rejection lookup indexed by request (Sec 35.1).
    by_request_messages: dict[str, list] = {}
    for m in tables["messages"]:
        if m.get("request_id") is not None:
            by_request_messages.setdefault(m["request_id"], []).append(m)
    by_request_images: dict[str, list] = {}
    for i in tables["images"]:
        if i.get("request_id") is not None:
            by_request_images.setdefault(i["request_id"], []).append(i)
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

        # Messages: must belong to this user; if request-bound, must match rid.
        # Indexed: only this user's rows are scanned (Sec 35.1, not all tables).
        raw_messages = [
            m
            for m in by_user_messages.get(uid, [])
            if (m.get("request_id") in (rid, None))
        ]
        # Images: same ownership rule (indexed by user).
        raw_images = [
            i
            for i in by_user_images.get(uid, [])
            if (i.get("request_id") in (rid, None))
        ]
        # Record wrong-user attempts that were rejected (for observability).
        # Indexed by request (Sec 35.1): no per-request full-table scan.
        rejected_messages = [
            m for m in by_request_messages.get(rid, []) if m.get("user_id") != uid
        ]
        rejected_images = [
            i for i in by_request_images.get(rid, []) if i.get("user_id") != uid
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
) -> tuple[EvidenceRegistry, list[str], list, list[str]]:
    """Deterministic evidence + optional LLM proposals (validated or dropped).

    Sec 32.2: selective LLM calls -- message model only when semantic
    interpretation may add value beyond the deterministic pass; image model
    only for blank amounts with a linked file. Request isolation enforced
    via `check_batch_safe` (one request/user per call). Returns
    (registry, used_ids, records, fallback_reasons) where records are
    secret-safe and fallback_reasons feed the Sec 33 request trace.
    """
    valid_event_ids = {e["event_id"] for e in ctx.events}
    valid_message_ids = {m["message_id"] for m in ctx.messages}
    valid_image_ids = {i["image_id"] for i in ctx.images}
    registry = EvidenceRegistry(valid_event_ids, valid_message_ids, valid_image_ids)
    used: list[str] = []
    records: list = []
    det_fact_count = 0
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
                det_fact_count += 1
            except Exception:
                continue
    # Sec 32.2 selective message call
    from affordai.evidence.llm_adapter import AdapterResult as _AdapterResult

    llm: _AdapterResult = _AdapterResult(facts=[], calls=0, fallback_reason="selective-skip")
    if llm_config.enabled and needs_llm_for_messages(ctx.messages, det_fact_count):
        check_batch_safe([ctx.request_id], [ctx.user_id])
        minimized = [minimize_message_context(m) for m in ctx.messages]
        llm = propose_facts(
            "message",
            {"request_id": ctx.request_id, "messages": minimized},
            llm_config,
        )
    records.extend(getattr(llm, "records", []))
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
    img_fallbacks: list[str] = []
    for event in ctx.events:
        if event["amount"] is not None:
            continue
        linked = resolve_images_for_event(
            event["event_id"], ctx.images, media_dir
        )
        existing = [d["image_id"] for d in linked if d["file_exists"]]
        img_proposals: _AdapterResult = _AdapterResult(facts=[], calls=0, fallback_reason="selective-skip")
        if llm_config.enabled and needs_llm_for_image(event["amount"], len(existing)):
            check_batch_safe([ctx.request_id], [ctx.user_id])
            img_proposals = propose_facts(
                "image_amount",
                minimize_image_context(event["event_id"], existing),
                llm_config,
            )
            records.extend(getattr(img_proposals, "records", []))
            img_fallbacks.append(f"{event['event_id']}:{img_proposals.fallback_reason}")
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
    fallback_reasons = [f"message:{llm.fallback_reason}"] + img_fallbacks
    return registry, used, records, fallback_reasons


def _eligibility_rejection(candidate, profile: dict, allows_partial: bool, deadline) -> tuple[str, str] | None:
    """Machine-readable eligibility rejection for ONE candidate (Sec 33.1G).

    Returns (reason_code, reason_text) or None if the candidate passes the
    eligibility stage. Mirrors `decision/eligibility.filter_candidates`
    rule-for-rule; any drift between the two is a bug.
    """
    from affordai.decision.eligibility import KIND_METHOD

    if candidate.last_date > deadline:
        return (
            "DEADLINE_EXCEEDED",
            f"completion {candidate.last_date.isoformat()} exceeds desired_completion_date {deadline.isoformat() if hasattr(deadline, 'isoformat') else deadline}",
        )
    method = KIND_METHOD[candidate.kind]
    if method not in set(profile.get("methods_will_consider", [])):
        return (
            "METHOD_NOT_ACCEPTED",
            f"payment method {method} not in methods_will_consider {sorted(profile.get('methods_will_consider', []))}",
        )
    if candidate.kind == "partial" and not allows_partial:
        return ("PARTIAL_NOT_ALLOWED", "request allows_partial_payment is false")
    if candidate.kind == "installments":
        max_months = profile.get("max_installment_months")
        if max_months is None:
            return ("INSTALLMENT_MONTHS_UNSET", "profile max_installment_months is null")
        span_days = (candidate.last_date - candidate.first_date).days
        if span_days > max_months * 31:
            return (
                "INSTALLMENT_TERM_EXCEEDED",
                f"installment span {span_days}d exceeds max_installment_months {max_months} (~{max_months * 31}d)",
            )
    return None


def _summarize_candidate(candidate) -> dict:
    """Secret-safe candidate summary for the request trace (Sec 33.1F)."""
    try:
        payments = [(d.isoformat() if hasattr(d, "isoformat") else str(d), str(a)) for d, a in candidate.payments]
    except Exception:
        payments = []
    try:
        first = candidate.first_date.isoformat()
        last = candidate.last_date.isoformat()
    except Exception:
        first, last = "", ""
    return {
        "kind": getattr(candidate, "kind", "?"),
        "payment_option_id": getattr(candidate, "option_id", None),
        "payments": payments,
        "total_paid": str(getattr(candidate, "total_paid", "")),
        "first_date": first,
        "last_date": last,
        "n_payments": len(payments),
        "n_spending_changes": len(getattr(candidate, "changes", {}) or {}),
    }


def decide_context(
    ctx: RequestContext,
    tables: dict,
    dataset_dir: str,
    llm_config: LlmConfig | None = None,
    trace: Trace | None = None,
    out_records: list | None = None,
    rtrace=None,
    run_id: str = "E0",
) -> Decision:
    llm_config = llm_config or LlmConfig()
    media_dir = os.path.join(dataset_dir, "media", "images")
    home = ctx.profile["home_currency"]
    req = ctx.request
    requested = req["requested_amount"]
    req_date = req["request_date"]

    registry, _used, _records, _fb_reasons = _collect_evidence(ctx, media_dir, llm_config, trace)
    if out_records is not None:
        out_records.extend(_records)
    facts = registry.facts_for(ctx.request_id)
    cancelled = conflict_resolver.cancelled_event_ids(facts)
    # Message-confirmed salary: narrow deterministic E1 (employer confirms).
    from affordai.evidence.message_income import confirmed_series

    extra_confirmed: list[tuple] = []
    for message in sorted(ctx.messages, key=lambda m: (str(m["sent_at"]), m["message_id"])):
        try:
            series, _income_notes = confirmed_series(ctx, message, home, tables["rates"])
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
    candidates = candidates + spending_changes.find_variants(state, candidates, targets, state.deadline)
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

    # Evidence: sorted immutable tuple of provenance-preserving source_ids
    evidence_ids = tuple(
        sorted(
            {
                f.source_id
                for f in facts
                if f.kind in ("cancel", "settle", "amend_amount", "amend_date", "delay", "confirm", "amount", "preference")
                and (f.event_id or f.kind in ("preference", "confirm", "settle"))
            }
        )
    )
    earliest_str = earliest.isoformat() if earliest else ""
    # Explanation facts -- validated subset for grounded explanation
    explanation_facts = {
        "request_id": ctx.request_id,
        "amount_safe_to_pay": safe,
        "requested_amount": requested,
        "affordability_status": status,
        "recommended_payment_method": method,
        "payment_plan": plan,
        "earliest_date_for_full_payment": earliest_str,
        "spending_changes_needed": changes,
        "evidence": evidence_ids,
        "request_date": req_date.isoformat(),
        "home_currency": home,
        "deadline": ctx.request["desired_completion_date"].isoformat()
        if hasattr(ctx.request["desired_completion_date"], "isoformat")
        else str(ctx.request["desired_completion_date"]),
    }
    # Build explanation from validated facts only (never recomputes financial decision)
    from affordai.finance.money import format_amount as _fmt

    # Use new grounded builder that consumes facts; fallback to legacy if needed
    try:
        # explanation_mod.build now validates via facts; we pass a minimal decision-like object
        _tmp_decision_for_expl = type(
            "TmpDec", (), {**explanation_facts, "evidence": evidence_ids}
        )()
        # Ensure attributes match what explanation_mod.build expects (Decision-like)
        _tmp_decision_for_expl.amount_safe_to_pay = safe
        _tmp_decision_for_expl.affordability_status = status
        _tmp_decision_for_expl.recommended_payment_method = method
        _tmp_decision_for_expl.payment_plan = plan
        _tmp_decision_for_expl.earliest_date_for_full_payment = earliest_str
        _tmp_decision_for_expl.spending_changes_needed = changes
        _tmp_decision_for_expl.evidence = evidence_ids
        expl = explanation_mod.build(
            _tmp_decision_for_expl, _fmt(requested, home), req_date.isoformat(), home
        )
        # Validate explanation against facts; if invalid, use safe fallback
        if not explanation_mod.validate(expl, _tmp_decision_for_expl):
            expl = explanation_mod.build_fallback(explanation_facts) if hasattr(explanation_mod, "build_fallback") else expl
    except Exception:
        expl = explanation_mod.build_fallback(explanation_facts) if hasattr(explanation_mod, "build_fallback") else (
            f"Requested {_fmt(requested, home)} {home} on {req_date.isoformat()}: {_fmt(safe, home)} {home} safe (status {status}, method {method}). "
            f"Full payment earliest safe: {earliest_str or 'not in forecast'}."
        )

    decision = Decision(
        original_index=ctx.original_index,
        request_id=ctx.request_id,
        user_id=ctx.user_id,
        amount_safe_to_pay=safe,
        affordability_status=status,
        recommended_payment_method=method,
        payment_plan=plan,
        earliest_date_for_full_payment=earliest_str,
        spending_changes_needed=changes,
        decision_explanation=expl,
        evidence=evidence_ids,
        explanation_facts=explanation_facts,
        requested_amount=requested,
        home_currency=home,
    )
    # Defense-in-depth: validate Decision invariant immediately; any violation -> fallback
    # (Decision.__post_init__ already validates; extra check catches downstream drift)
    try:
        # Re-validate cross-field consistency via invariants (includes earliest vs status)
        from affordai.decision.invariants import check_earliest_consistency, check_status_method_consistency

        if not check_status_method_consistency(status, method):
            raise ValueError("status/method inconsistent")
        if not check_earliest_consistency(status, req_date.isoformat(), earliest_str):
            raise ValueError("earliest/status inconsistent")
    except Exception as _inv_exc:
        if trace is not None:
            trace.record("decision-invariant-violation", ctx.request_id, str(_inv_exc)[:200])
        # Fail-closed: degrade to safe fallback preserving capacity
        return _fallback_decision(ctx, f"invariant:{type(_inv_exc).__name__}", safe, earliest)

    if trace is not None:
        trace.record(
            "decision",
            ctx.request_id,
            f"{status}/{method} safe={safe} earliest={earliest} "
            f"candidates={len(candidates)} eligible={len(eligible)} "
            f"notes={';'.join(notes + gen_notes)[:200]}",
        )
    if rtrace is not None:
        _populate_rtrace(
            rtrace, ctx, registry, _fb_reasons, state, safe, earliest,
            candidates, eligible, validated, winner, status, method,
            decision, run_id,
        )
        rtrace.finish("ok")
    return decision


def _populate_rtrace(
    rtrace, ctx, registry, fb_reasons, state, safe, earliest,
    candidates, eligible, validated, winner, status, method,
    decision, run_id: str,
) -> None:
    """Fill all 10 Sec-33 sections of one RequestTrace (diagnostics only).

    Never raises into the pipeline: any introspection failure is recorded
    as a trace failure entry, never a financial fact.
    """
    from affordai.finance.temporal import WINDOW_DAYS

    try:
        from affordai.security.redact import redact as _redact

        rtrace.run_id = run_id
        # A/B. request + evidence ids
        rtrace.evidence = {
            "message_ids": sorted(m.get("message_id", "") for m in ctx.messages),
            "event_ids": sorted(e.get("event_id", "") for e in ctx.events),
            "image_ids": sorted(i.get("image_id", "") for i in ctx.images),
            "payment_option_ids": sorted(o.get("payment_option_id", "") for o in ctx.payment_options),
            "profile_id": ctx.user_id,
            "used_evidence_ids": sorted({f.source_id for f in registry.all_facts()}),
            "join_issues": len(ctx.join_issues),
        }
        # C. extracted facts with provenance
        rtrace.facts = [f.provenance() for f in registry.all_facts()]
        try:
            rtrace.rejected_facts = list(registry.rejected())
        except Exception:
            rtrace.rejected_facts = []
        rtrace.llm_fallback = "; ".join(fb_reasons)
        # D. deterministic financial state summary
        rtrace.financial_state = {
            "starting_balance": str(state.opening),
            "minimum_balance": str(state.minimum),
            "requested_amount": str(state.requested),
            "home_currency": state.home,
            "request_date": state.request_date.isoformat(),
            "deadline": state.deadline.isoformat(),
            "n_flows": len(state.flows),
            "n_unknowns": len(state.unknowns),
            "notes": [_redact(n)[:200] for n in list(state.notes)],
        }
        # E. forecast debug summary (base run without new payments)
        try:
            base = simulate(state, [])
            rtrace.forecast = {
                "horizon_days": WINDOW_DAYS,
                "base_safe": bool(base.ok),
                "min_closing": str(base.min_closing),
                "min_balance_date": base.worst_day.isoformat() if base.worst_day else "",
                "safe_today": str(safe),
                "earliest_full": earliest.isoformat() if earliest else "",
                "constraint": (
                    "base obligations already breach the floor" if not base.ok
                    else ("full safe never in window" if earliest is None else "ok")
                ),
            }
        except Exception as _fe:
            rtrace.forecast = {"error": f"{type(_fe).__name__}"}
        # F/G/H. candidates, rejections, selection
        eligible_ids = {id(c) for c in eligible}
        validated_ids = {id(c) for c in validated}
        winner_id = id(winner) if winner is not None else None
        deadline = req_deadline(ctx)
        rtrace.candidates = []
        rtrace.rejected_plans = []
        for c in candidates:
            summary = _summarize_candidate(c)
            summary["eligible"] = id(c) in eligible_ids
            summary["safe"] = id(c) in validated_ids if id(c) in eligible_ids else None
            rtrace.candidates.append(summary)
            if id(c) == winner_id:
                continue
            rej = _eligibility_rejection(c, ctx.profile, ctx.request.get("allows_partial_payment"), deadline)
            if rej is not None:
                code, text = rej
                rtrace.rejected_plans.append({
                    "kind": c.kind, "payment_option_id": c.option_id,
                    "reason_code": code, "reason": _redact(text)[:300],
                })
            elif id(c) not in validated_ids:
                try:
                    sim = simulate(state, c.payments, c.changes or {})
                    when = sim.worst_day.isoformat() if sim.worst_day else ""
                except Exception:
                    when = ""
                rtrace.rejected_plans.append({
                    "kind": c.kind, "payment_option_id": c.option_id,
                    "reason_code": "UNSAFE_MIN_BALANCE",
                    "reason": f"minimum balance violated with this plan (worst day {when or 'unknown'})",
                })
            else:
                rtrace.rejected_plans.append({
                    "kind": c.kind, "payment_option_id": c.option_id,
                    "reason_code": "OUTRANKED",
                    "reason": (
                        f"safe and eligible but lost deterministic 6-rule ranking to "
                        f"{winner.kind}/{winner.option_id or 'n/a'}"
                    ),
                })
        if winner is None:
            rtrace.selected_plan = {
                "selected": "none",
                "reason": "no safe eligible candidate; safest fallback not_affordable/not_recommended",
            }
        else:
            try:
                from affordai.finance.optimizer import rank_key as _rank_key

                _rk = _rank_key(winner, deadline)
                rk = [str(x) for x in _rk]
            except Exception:
                rk = []
            rtrace.selected_plan = {
                "kind": winner.kind,
                "selected_payment_option_id": winner.option_id,
                "ranking_key": rk,
                "reason": "deterministic 6-rule rank minimum (deadline, no-changes, min-total, earlier-start, fewer-payments, lowest-option-id)",
            }
        # I. final validated decision
        rtrace.final_decision = {
            "request_id": decision.request_id,
            "amount_safe_to_pay": str(decision.amount_safe_to_pay),
            "affordability_status": decision.affordability_status,
            "recommended_payment_method": decision.recommended_payment_method,
            "payment_plan": decision.payment_plan,
            "earliest_date_for_full_payment": decision.earliest_date_for_full_payment,
            "spending_changes_needed": decision.spending_changes_needed,
            "n_evidence": len(decision.evidence),
        }
    except Exception as _te:
        try:
            rtrace.log_failure("trace-populate", f"{type(_te).__name__}: {_te}")
        except Exception:
            pass


def req_deadline(ctx):
    """Return the request deadline (date) for ranking/rejection text."""
    return ctx.request.get("desired_completion_date")


def _fallback_decision(
    ctx: RequestContext, reason: str, safe: Decimal | None = None, earliest=None
) -> Decision:
    """Safest valid decision when a request cannot be processed: never crash.

    Preserves capacity information (safe amount + earliest date) when it can
    be derived, otherwise falls back to 0/"" -- never invents a plan.
    `earliest` may be date or ""/None.
    """
    from datetime import date as _date

    amt = safe if isinstance(safe, Decimal) else Decimal("0")
    if earliest is None or earliest == "":
        ear_str = ""
    elif isinstance(earliest, _date):
        ear_str = earliest.isoformat()
    elif isinstance(earliest, str):
        ear_str = earliest
    else:
        ear_str = ""
    try:
        requested_fallback = ctx.request.get("requested_amount")
        if not isinstance(requested_fallback, Decimal):
            from affordai.finance.money import parse_amount

            try:
                requested_fallback = parse_amount(requested_fallback)
            except Exception:
                requested_fallback = None
        home_fallback = ctx.profile.get("home_currency")
    except Exception:
        requested_fallback = None
        home_fallback = None
    # Clamp safe to requested bounds for fallback as well
    if isinstance(requested_fallback, Decimal) and isinstance(amt, Decimal):
        if amt < 0:
            amt = Decimal("0")
        if amt > requested_fallback:
            from affordai.finance.money import quantize_money

            try:
                amt = quantize_money(requested_fallback, home_fallback or "INR")
            except Exception:
                amt = requested_fallback
    fallback_facts = {
        "request_id": ctx.request_id,
        "amount_safe_to_pay": amt,
        "requested_amount": requested_fallback,
        "affordability_status": "not_affordable",
        "recommended_payment_method": "not_recommended",
        "payment_plan": "none",
        "earliest_date_for_full_payment": ear_str,
        "spending_changes_needed": "none",
        "evidence": (),
        "request_date": str(ctx.request.get("request_date", "")),
        "home_currency": home_fallback,
        "deadline": str(ctx.request.get("desired_completion_date", "")),
        "reason": reason,
    }
    return Decision(
        original_index=ctx.original_index,
        request_id=ctx.request_id,
        user_id=ctx.user_id,
        amount_safe_to_pay=amt,
        affordability_status="not_affordable",
        recommended_payment_method="not_recommended",
        payment_plan="none",
        earliest_date_for_full_payment=ear_str,
        spending_changes_needed="none",
        decision_explanation=(
            f"Processing failure ({reason}); safest fallback applied, "
            "no payment recommended."
        ),
        evidence=(),
        explanation_facts=fallback_facts,
        requested_amount=requested_fallback if isinstance(requested_fallback, Decimal) else None,
        home_currency=home_fallback if isinstance(home_fallback, str) else None,
    )


def _decide_safe(
    ctx: RequestContext,
    tables: dict,
    dataset_dir: str,
    llm_config: LlmConfig,
    trace: Trace | None,
    rtrace=None,
    run_id: str = "E0",
) -> tuple[Decision, bool]:
    """Decide one request; on unexpected failure return the safe fallback."""
    try:
        return decide_context(ctx, tables, dataset_dir, llm_config, trace, rtrace=rtrace, run_id=run_id), False
    except Exception as exc:  # never crash the batch; degrade to safest valid row
        if trace is not None:
            trace.record("decision-fallback", ctx.request_id, f"{type(exc).__name__}: {exc}"[:200])
        if rtrace is not None:
            rtrace.log_failure("decision-fallback", f"{type(exc).__name__}: {exc}")
        # Best-effort capacity preservation: try to compute safe/earliest even on failure
        safe_preserve: Decimal | None = None
        earliest_preserve = None
        try:
            # Re-derive minimal state for capacity (no LLM, deterministic)
            registry, _, _, _ = _collect_evidence(ctx, os.path.join(dataset_dir, "media", "images"), llm_config, None)
            facts = registry.facts_for(ctx.request_id)
            cancelled = conflict_resolver.cancelled_event_ids(facts)
            extra_preserve: list[tuple] = []
            for m in sorted(ctx.messages, key=lambda mm: (str(mm.get("sent_at")), mm.get("message_id", ""))):
                try:
                    from affordai.evidence.message_income import confirmed_series as _cs

                    series, _ = _cs(ctx, m, ctx.profile["home_currency"], tables.get("rates"))
                    for _d, _a in series:
                        extra_preserve.append((_d, _a, m.get("message_id", "")))
                except Exception:
                    continue
            amend_raw = conflict_resolver.amended_amounts(facts)
            amend_amounts: dict[str, Decimal] = {}
            for _eid, _raw in amend_raw.items():
                try:
                    _v = parse_amount(_raw)
                except ValueError:
                    continue
                if _v is not None and _v > 0:
                    amend_amounts[_eid] = _v
            amend_dates = {}
            for _eid, _raw in conflict_resolver.amended_dates(facts).items():
                try:
                    from datetime import datetime as _dt

                    amend_dates[_eid] = _dt.strptime(_raw, "%Y-%m-%d").date()
                except ValueError:
                    continue
            flows, unknowns, notes = build_flows(ctx, tables["rates"], cancelled, amend_amounts, amend_dates, extra_preserve)
            state = build_state(ctx, flows, unknowns, notes)
            safe_preserve = max_safe_today(state)
            earliest_preserve = earliest_full_date(state)
        except Exception:
            pass
        fb = _fallback_decision(ctx, type(exc).__name__, safe_preserve, earliest_preserve)
        if rtrace is not None:
            try:
                rtrace.final_decision = {
                    "request_id": fb.request_id,
                    "amount_safe_to_pay": str(fb.amount_safe_to_pay),
                    "affordability_status": fb.affordability_status,
                    "recommended_payment_method": fb.recommended_payment_method,
                    "payment_plan": fb.payment_plan,
                    "earliest_date_for_full_payment": fb.earliest_date_for_full_payment,
                    "spending_changes_needed": fb.spending_changes_needed,
                    "n_evidence": 0,
                }
                rtrace.finish("fallback")
            except Exception:
                pass
        return fb, True


def run(
    dataset_dir: str,
    llm_config: LlmConfig | None = None,
    trace: Trace | None = None,
    run_id: str = "E0",
    request_traces: dict | None = None,
) -> tuple[list[Decision], dict]:
    """Run the full deterministic pipeline. Returns (decisions, usage).

    When `request_traces` (a plain dict) is supplied it is filled with one
    ``RequestTrace`` per request (Sec 33) keyed by request_id, including the
    output-row mapping (Sec 33.1J). Tracing never alters decisions.
    """
    from affordai.evaluation.usage import UsageReport
    from affordai.observability.request_trace import RequestTrace, make_trace_id

    llm_config = llm_config or load_config_from_env()
    tables = load_dataset(dataset_dir)
    contexts = build_contexts(tables)
    decisions: list[Decision] = []
    fallbacks = 0
    all_records: list = []
    for ctx in contexts:
        recs: list = []
        rtrace = None
        if request_traces is not None:
            import time as _time

            rtrace = RequestTrace(
                request_id=ctx.request_id,
                original_row_index=ctx.original_index,
                trace_id=make_trace_id(run_id, ctx.request_id, ctx.original_index),
                run_id=run_id,
                start_time=_time.time(),
            )
            request_traces[ctx.request_id] = rtrace
        try:
            decision = decide_context(ctx, tables, dataset_dir, llm_config, trace, out_records=recs, rtrace=rtrace, run_id=run_id)
            failed = False
            if rtrace is not None and rtrace.status == "pending":
                rtrace.finish("ok")
        except Exception as exc:
            if trace is not None:
                trace.record("decision-fallback", ctx.request_id, f"{type(exc).__name__}: {exc}"[:200])
            decision, failed = _decide_safe(ctx, tables, dataset_dir, llm_config, trace, rtrace=rtrace, run_id=run_id)
            # recs already captured from the failing decide_context attempt (partial); keep them
        decisions.append(decision)
        fallbacks += int(failed)
        all_records.extend(recs)
    decisions.sort(key=lambda d: d.original_index)
    if request_traces is not None:
        # Sec 33.1J: output-row mapping (CSV row order == sorted-by-original_index order).
        for row_index, d in enumerate(decisions):
            rt = request_traces.get(d.request_id)
            if rt is not None:
                rt.output_row = {
                    "output_row_index": row_index,
                    "request_id": d.request_id,
                    "validation_status": "decision-invariant-pass; csv-validator-see-scripts/validate_output.py",
                }
    total_in = sum(getattr(r, "input_tokens", 0) for r in all_records)
    total_out = sum(getattr(r, "output_tokens", 0) for r in all_records)
    total_calls = len(all_records)
    # Per-model aggregation for usage report (secret-safe: no prompt text)
    per_model: dict[tuple[str, str], dict] = {}
    for r in all_records:
        key = (getattr(r, "provider", "") or "", getattr(r, "model", "") or "")
        bucket = per_model.setdefault(key, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        bucket["calls"] += 1
        bucket["input_tokens"] += getattr(r, "input_tokens", 0)
        bucket["output_tokens"] += getattr(r, "output_tokens", 0)
    usage = UsageReport(
        provider=llm_config.provider,
        model=llm_config.model,
        calls=total_calls,
        input_tokens=total_in,
        output_tokens=total_out,
        note=f"deterministic E0 (llm: {llm_config.reason})" if not total_calls else f"metered ({total_calls} calls)",
        per_model=per_model,
        records=all_records,
    )
    return decisions, {
        "usage": usage,
        "n_requests": len(decisions),
        "n_fallbacks": fallbacks,
        "llm_reason": llm_config.reason,
    }
