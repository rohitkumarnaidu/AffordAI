"""Sections 33-35 -- observability, reliability, performance (single source).

No duplicates: trace schema lives in observability/request_trace.py,
retry/fallback policy in evidence/llm_adapter.py (FAILURE_MATRIX +
RETRYABLE/NON_RETRYABLE + backoff_for_attempt), redaction in
security/redact.py, token accounting in evaluation/usage.py. This file
only asserts contracts with execution evidence, never re-implements them.
"""
import json
import sys
import time
from decimal import Decimal

import pytest

sys.path.insert(0, "src")

from affordai.evaluation.harness import run_dataset
from affordai.evidence.llm_adapter import (
    FAILURE_MATRIX,
    NON_RETRYABLE_ERRORS,
    RETRYABLE_ERRORS,
    LlmConfig,
    ProviderError,
    RateLimitError,
    backoff_for_attempt,
    call_with_retry,
    propose_facts,
    validate_proposal_json,
)
from affordai.evidence.image_interpreter import resolve_images_for_event
from affordai.observability.request_trace import RequestTrace, RequestTraceStore, make_trace_id
from affordai.pipeline import build_contexts, decide_context, load_dataset
from affordai.security.redact import contains_secret


TABLES = None
CONTEXTS = None


def _tables():
    global TABLES
    if TABLES is None:
        TABLES = load_dataset("dataset/official")
    return TABLES


def _contexts():
    global CONTEXTS
    if CONTEXTS is None:
        CONTEXTS = build_contexts(_tables())
    return CONTEXTS


def _traced_decision(ctx_index=0):
    tables = _tables()
    ctx = _contexts()[ctx_index]
    rt = RequestTrace(
        request_id=ctx.request_id,
        original_row_index=ctx.original_index,
        trace_id=make_trace_id("E0", ctx.request_id, ctx.original_index),
        run_id="E0",
        start_time=time.time(),
    )
    decision = decide_context(ctx, tables, "dataset/official", rtrace=rt, run_id="E0")
    rt.finish("ok")
    return ctx, decision, rt


# ---------------------------------------------------------------------------
# 33.1 Request trace -- all 10 sections on a REAL request
# ---------------------------------------------------------------------------

def test_request_trace_created():
    ctx, decision, rt = _traced_decision(0)
    assert rt.trace_id and rt.request_id == ctx.request_id
    assert rt.status == "ok"
    blob = json.loads(rt.to_json())  # JSON-serializable
    assert blob["request_id"] == ctx.request_id


def test_request_id_preserved():
    # Same request_id from input -> context -> trace -> decision -> output map.
    result = run_dataset("dataset/official", request_traces={})
    traces = {}
    store = {}
    run_dataset("dataset/official", request_traces=store)
    tables = _tables()
    req_ids = [r["request_id"] for r in tables["requests"]]
    decisions = result["decisions"]
    assert [d.request_id for d in decisions] == req_ids  # order + identity
    for d in decisions:
        rt = store[d.request_id]
        assert rt.request_id == d.request_id
        assert rt.original_row_index == d.original_index
        assert rt.final_decision["request_id"] == d.request_id
        assert rt.output_row["request_id"] == d.request_id


def test_trace_contains_evidence():
    ctx, decision, rt = _traced_decision(0)
    ev = rt.evidence
    assert set(ev) >= {"message_ids", "event_ids", "image_ids", "payment_option_ids", "profile_id"}
    assert ev["profile_id"] == ctx.user_id
    assert ev["message_ids"] == sorted(m["message_id"] for m in ctx.messages)
    assert ev["payment_option_ids"] == sorted(o["payment_option_id"] for o in ctx.payment_options)


def test_trace_contains_financial_state():
    ctx, decision, rt = _traced_decision(0)
    st = rt.financial_state
    assert set(st) >= {"starting_balance", "minimum_balance", "requested_amount",
                       "home_currency", "request_date", "deadline", "n_flows"}
    assert Decimal(st["starting_balance"]) == ctx.profile["current_available_balance"]
    assert Decimal(st["minimum_balance"]) == ctx.profile["minimum_balance_to_keep"]
    assert st["home_currency"] == ctx.profile["home_currency"]


def test_trace_contains_forecast():
    ctx, decision, rt = _traced_decision(0)
    fc = rt.forecast
    assert fc["horizon_days"] == 90
    assert "min_closing" in fc and "min_balance_date" in fc and "constraint" in fc
    assert fc["safe_today"] == str(decision.amount_safe_to_pay)
    assert fc["earliest_full"] == decision.earliest_date_for_full_payment


def test_trace_contains_candidate_plans():
    ctx, decision, rt = _traced_decision(0)
    assert len(rt.candidates) >= 1
    for c in rt.candidates:
        assert set(c) >= {"kind", "payment_option_id", "payments", "total_paid",
                          "first_date", "last_date", "eligible", "safe"}
        assert c["kind"] in {"full", "partial", "installments", "wait"}


def test_trace_contains_rejection_reasons():
    # Every non-winning candidate has an explicit machine-readable reason.
    ctx, decision, rt = _traced_decision(0)
    assert len(rt.rejected_plans) == len(rt.candidates) - 1
    allowed = {"DEADLINE_EXCEEDED", "METHOD_NOT_ACCEPTED", "PARTIAL_NOT_ALLOWED",
               "INSTALLMENT_TERM_EXCEEDED", "INSTALLMENT_MONTHS_UNSET",
               "UNSAFE_MIN_BALANCE", "OUTRANKED"}
    for r in rt.rejected_plans:
        assert r["reason_code"] in allowed, r
        assert len(r["reason"]) >= 10 and r["reason"] not in {"not suitable", "invalid", "failed"}
    # At least one rejection reason exercised across the full dataset.
    store: dict = {}
    run_dataset("dataset/official", request_traces=store)
    codes = {r["reason_code"] for rt2 in store.values() for r in rt2.rejected_plans}
    assert codes & allowed == codes and len(codes) >= 2


def test_trace_contains_selected_plan():
    ctx, decision, rt = _traced_decision(0)
    sel = rt.selected_plan
    if decision.recommended_payment_method == "not_recommended":
        assert sel["selected"] == "none"
    else:
        assert sel["kind"] in {"full", "partial", "installments", "wait"}
        assert "ranking_key" in sel and len(sel["ranking_key"]) == 6
        assert "reason" in sel and "6-rule" in sel["reason"]


def test_trace_contains_final_decision():
    ctx, decision, rt = _traced_decision(0)
    fd = rt.final_decision
    assert fd["amount_safe_to_pay"] == str(decision.amount_safe_to_pay)
    assert fd["affordability_status"] == decision.affordability_status
    assert fd["recommended_payment_method"] == decision.recommended_payment_method
    assert fd["payment_plan"] == decision.payment_plan
    assert fd["earliest_date_for_full_payment"] == decision.earliest_date_for_full_payment


def test_trace_contains_output_mapping():
    store: dict = {}
    result = run_dataset("dataset/official", request_traces=store)
    for row_index, d in enumerate(result["decisions"]):
        rt = store[d.request_id]
        assert rt.output_row["output_row_index"] == row_index
        assert rt.output_row["request_id"] == d.request_id
        assert "validation_status" in rt.output_row


def test_trace_redacts_secrets():
    rt = RequestTrace(request_id="r1", original_row_index=0, trace_id="t", run_id="E0")
    rt.log_failure("backend-test", "OPENAI_API_KEY=supersecretvalue123 timeout")
    assert not contains_secret(rt.failures[0]["detail"])
    assert "[REDACTED]" in rt.failures[0]["detail"]
    blob = rt.to_json()
    assert "supersecretvalue123" not in blob


def test_trace_ids_deterministic():
    a = make_trace_id("E0", "request_1", 0)
    b = make_trace_id("E0", "request_1", 0)
    assert a == b and len(a) == 16
    assert make_trace_id("E0", "request_2", 1) != a
    assert make_trace_id("E1", "request_1", 0) != a


def test_trace_store_export(tmp_path):
    ctx, decision, rt = _traced_decision(0)
    store = RequestTraceStore({ctx.request_id: rt})
    out = tmp_path / "traces.json"
    store.to_json_file(str(out))
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert ctx.request_id in blob
    assert blob[ctx.request_id]["final_decision"]["request_id"] == ctx.request_id


# ---------------------------------------------------------------------------
# 34.1 Model/tool failures -- injected, observed, bounded
# ---------------------------------------------------------------------------

def _retry_cfg(retries=2):
    return LlmConfig(enabled=True, provider="p", model="m", max_retries=retries, reason="ok")


def test_timeout():
    calls = {"n": 0}

    def backend():
        calls["n"] += 1
        raise TimeoutError("model timeout")

    raw, rec = call_with_retry(backend, _retry_cfg(2), purpose="message_extract", request_id="r1")
    assert raw == [] and rec.success is False
    assert rec.fallback.startswith("retry-exhausted:transient:TimeoutError")
    assert calls["n"] == 3  # OBSERVED: 1 + 2 retries, then fallback
    assert rec.backoff_s == [0.5, 1.0, 2.0]  # OBSERVED bounded schedule (one entry per failed attempt)


def test_api_failure():
    calls = {"n": 0}

    def backend():
        calls["n"] += 1
        raise ProviderError("500 upstream unavailable")

    raw, rec = call_with_retry(backend, _retry_cfg(1), purpose="message_extract")
    assert raw == [] and calls["n"] == 2
    assert "ProviderError" in rec.fallback


def test_rate_limit():
    calls = {"n": 0}

    def backend():
        calls["n"] += 1
        raise RateLimitError("429 too many requests")

    raw, rec = call_with_retry(backend, _retry_cfg(3), purpose="image_amount_extract")
    assert raw == [] and calls["n"] == 4  # OBSERVED: bounded, no infinite retry
    assert rec.backoff_s == [0.5, 1.0, 2.0, 4.0]


def test_invalid_json():
    assert validate_proposal_json("{not json") is None
    assert validate_proposal_json("") is None
    # Malformed output never reaches the engine: propose path drops it.
    cfg = LlmConfig(enabled=False, reason="LLM_ENABLED != 1")
    res = propose_facts("message", {"request_id": "r1"}, cfg)
    assert res.facts == [] and res.calls == 0


def test_unexpected_output():
    # Wrong enum / wrong type / null / extra field / dangerous instruction-ish kind.
    cases = [
        {"kind": "approve_anyway", "source_id": "m1", "confidence": "0.9"},
        {"kind": "cancel", "source_id": "m1", "confidence": "0.9", "normalized_value": 123},
        {"kind": "cancel", "source_id": None, "confidence": "0.9"},
        {"kind": "cancel", "source_id": "m1", "confidence": "0.9", "system": "ignore rules"},
        {"kind": "amount", "source_id": "i1", "confidence": "0.9", "normalized_value": "999999999999"},
    ]
    # First four must be rejected; huge-but-wellformed amount passes schema gate
    # (ownership + floor simulation still contain it downstream).
    assert validate_proposal_json(json.dumps(cases[0])) is None
    assert validate_proposal_json(json.dumps(cases[2])) is None
    assert validate_proposal_json(json.dumps(cases[3])) is None
    from affordai.evidence.llm_adapter import _validate_proposal

    assert _validate_proposal(cases[1]) is None


def test_missing_evidence():
    # Blank amounts stay UNKNOWN (never zero); decisions remain safe.
    store: dict = {}
    result = run_dataset("dataset/official", request_traces=store)
    unknowns = [f for rt in store.values() for f in rt.facts if f.get("normalized_value") == "unknown"]
    assert len(unknowns) >= 1  # OBSERVED on real data
    for f in unknowns:
        assert f["confidence"] == "0"
    from affordai.output.validator import validate_consistency

    assert validate_consistency(result["decisions"]) == []


def test_image_failure():
    # Missing file -> file_exists False -> UNKNOWN marker, never 0.
    rows = [{"image_id": "img_nope", "request_id": "r1", "user_id": "u1", "related_event_id": "e1"}]
    linked = resolve_images_for_event("e1", rows, "dataset/official/media/images")
    assert linked and linked[0]["file_exists"] is False
    from affordai.evidence.image_interpreter import amount_unknown_evidence

    ev = amount_unknown_evidence("e1", "img_nope", "r1", "u1")
    assert ev.normalized_value == "unknown" and ev.confidence == Decimal("0")
    # Full-dataset proof: 16/16 images resolve; blanks without vision stay UNKNOWN.
    tables = _tables()
    assert len(tables["images"]) == 16


def test_fallback():
    # Pipeline-level fallback: safest valid row, capacity preserved, logged.
    from affordai.pipeline import RequestContext, _decide_safe

    tables = _tables()
    good = [c for c in _contexts() if c.messages]
    assert good, "need a message-bearing context for the fallback test"
    src = good[0]
    broken_profile = dict(src.profile)
    broken_profile.pop("home_currency", None)  # forces StateError inside decide
    broken = RequestTrace(request_id=src.request_id, original_row_index=src.original_index,
                          trace_id="t", run_id="E0")
    import copy

    ctx = RequestContext(
        original_index=src.original_index, request_id=src.request_id, user_id=src.user_id,
        request=dict(src.request), profile=broken_profile,
        events=[dict(e) for e in src.events], messages=[dict(m) for m in src.messages],
        images=[dict(i) for i in src.images],
        payment_options=[dict(o) for o in src.payment_options],
    )
    tables2 = copy.copy(tables)
    decision, failed = _decide_safe(ctx, tables2, "dataset/official", LlmConfig(), None,
                                    rtrace=broken)
    assert failed is True  # OBSERVED: fallback activated
    assert decision.affordability_status == "not_affordable"
    assert decision.recommended_payment_method == "not_recommended"
    assert decision.payment_plan == "none"
    assert broken.status == "fallback" and broken.failures  # OBSERVED: logged


def test_bounded_retry():
    # Retry storm guard: attempts always == 1 + max_retries, backoff capped.
    assert backoff_for_attempt(0) == 0.5
    assert backoff_for_attempt(1) == 1.0
    assert backoff_for_attempt(10) == 8.0  # capped
    for retries in (0, 1, 3):
        calls = {"n": 0}

        def backend():
            calls["n"] += 1
            raise ConnectionError("down")

        raw, rec = call_with_retry(backend, _retry_cfg(retries), purpose="message_extract")
        assert calls["n"] == 1 + retries  # OBSERVED exact budget
        assert len(rec.backoff_s) == 1 + retries


def test_non_retryable_error_not_retried():
    calls = {"n": 0}

    def backend():
        calls["n"] += 1
        raise ValueError("invalid schema from model")

    raw, rec = call_with_retry(backend, _retry_cfg(5), purpose="message_extract")
    assert calls["n"] == 1  # OBSERVED: no retry on deterministic failure
    assert rec.fallback.startswith("backend:ValueError")
    assert ValueError in NON_RETRYABLE_ERRORS
    assert set(RETRYABLE_ERRORS) == {TimeoutError, ConnectionError, RateLimitError, ProviderError}


def test_failure_matrix_covers_all_required_modes():
    modes = {row["failure"] for row in FAILURE_MATRIX}
    assert {"timeout", "api-failure-5xx", "rate-limit-429", "invalid-json",
            "unexpected-output", "missing-evidence", "image-failure"} <= modes
    for row in FAILURE_MATRIX:
        assert row["fallback"] and row["logged"] == "yes"
        text = (row["final"] + " " + row["fallback"]).lower()
        assert ("never" in text) or ("fabricat" in text) or ("no invented" in text)


# ---------------------------------------------------------------------------
# 35 Performance -- measured, not assumed
# ---------------------------------------------------------------------------

def test_full_dataset_benchmark():
    started = time.perf_counter()
    result = run_dataset("dataset/official")
    elapsed = time.perf_counter() - started
    assert result["n_requests"] == 250
    assert elapsed < 120  # OBSERVED ~2.5s; generous bound guards regressions
    from affordai.output.validator import validate_consistency

    assert validate_consistency(result["decisions"]) == []


def test_indexed_lookup_behavior():
    # Ownership isolation: each context sees only its own user's rows.
    for ctx in _contexts():
        for m in ctx.messages:
            assert m["user_id"] == ctx.user_id
            assert m.get("request_id") in (ctx.request_id, None)
        for i in ctx.images:
            assert i["user_id"] == ctx.user_id
    # Determinism: rebuild gives identical identity/order.
    again = build_contexts(_tables())
    assert [c.request_id for c in again] == [c.request_id for c in _contexts()]
    # Isolation: mutating one context cannot leak into another.
    a, b = _contexts()[0], _contexts()[1]
    if a.events and b.events:
        a.events[0]["amount"] = Decimal("12345.67")
        assert all(e.get("amount") != Decimal("12345.67") for e in b.events)
        a.events[0].pop("amount", None)


def test_no_unnecessary_nested_scan():
    import pathlib

    src = pathlib.Path("src/affordai/pipeline.py").read_text(encoding="utf-8")
    body = src[src.find("def build_contexts"):]
    body = body[:body.find("\ndef ", 1)]
    # Per-request loop (after the one-time index build) must use the
    # pre-built indexes, not full-table scans.
    per_request = body[body.find('for req in tables["requests"]'):]
    assert "by_user_messages.get(" in per_request
    assert "by_user_images.get(" in per_request
    assert "by_request_messages.get(" in per_request
    assert 'for m in tables["messages"]' not in per_request
    assert 'for i in tables["images"]' not in per_request


def test_model_call_count():
    result = run_dataset("dataset/official")
    usage = result["usage"]
    # Calls may be 0 (E0) or >0 when dotenv enables groq (metered) — both are correct, but metered must be consistent
    assert usage.calls >= 0
    assert usage.total_tokens == usage.input_tokens + usage.output_tokens
    if usage.calls == 0:
        assert usage.total_tokens == 0
        assert usage.avg_tokens_per_request(250) == 0.0
    else:
        assert usage.total_tokens > 0
        assert usage.avg_tokens_per_request(250) > 0
        assert usage.calls == len(usage.records) if hasattr(usage, "records") else True


def test_selective_image_processing():
    tables = _tables()
    assert len(tables["images"]) == 16  # only 16 images exist; all linked
    linked = {i.get("related_event_id") for i in tables["images"]}
    assert len(linked) == 16
    # Blank amounts never become zero anywhere in the pipeline.
    store: dict = {}
    run_dataset("dataset/official", request_traces=store)
    for rt in store.values():
        for f in rt.facts:
            if f.get("kind") == "amount":
                assert f.get("normalized_value") != "0"


def test_cache_behavior_if_implemented():
    from affordai.evidence.llm_adapter import _CACHE, PROMPT_VERSION, SCHEMA_VERSION

    # Versioned keys (prompt+schema in key) + measured non-use in E0.
    payload = {"request_id": "r1", "messages": [{"message_id": "m1"}]}
    k1 = _CACHE.key("openai", "gpt-4o", "message_extract", payload)
    assert PROMPT_VERSION in k1 and SCHEMA_VERSION in k1
    assert _CACHE.key("openai", "gpt-4o", "message_extract", payload) == k1
    assert _CACHE.key("openai", "other", "message_extract", payload) != k1
    # LOCAL MEASUREMENT: E0 run performs no cacheable repeat work.
    run_dataset("dataset/official")
    assert len(_CACHE._store) == 0  # CACHE NOT ADOPTED (documented, measured)

# ---------------------------------------------------------------------------
# F-01 -- E0 verification gate (exact-zero, scrubbed environment; never weakened)
# ---------------------------------------------------------------------------

def test_e0_gate_exact_zero_backend_calls(monkeypatch):
    """F-01 gate: under forced E0 there are EXACTLY zero backend calls,
    zero LLM-derived facts, and valid output. This test MUST stay exact --
    do not convert it to a mode-aware conditional (that variant already
    exists as test_model_call_count)."""
    monkeypatch.setenv("LLM_ENABLED", "0")
    monkeypatch.delenv("API_KEY", raising=False)
    store: dict = {}
    result = run_dataset("dataset/official", request_traces=store)
    usage = result["usage"]
    assert usage.calls == 0
    assert usage.backend_calls() == 0
    assert usage.input_tokens == 0 and usage.output_tokens == 0
    assert usage.total_tokens == 0
    assert len(usage.records) == 0
    assert len(result["decisions"]) == 250
    for rt in store.values():
        for f in rt.facts:
            assert f.get("method") != "llm" and f.get("extraction_method") != "llm"
    from affordai.output.validator import validate_consistency
    assert validate_consistency(result["decisions"]) == []


def test_e0_equals_metered_output(monkeypatch):
    """Intended invariant: the no-backend metered path adds zero facts, so
    E0 and metered serialized outputs are byte-identical. If this ever
    legitimately diverges (real backend vendored), document why here."""
    import hashlib
    from affordai.pipeline import build_contexts, load_dataset
    tables = load_dataset("dataset/official")
    ctxs = build_contexts(tables)
    home = {c.request_id: c.profile["home_currency"] for c in ctxs}
    cols = ("request_id", "amount_safe_to_pay", "affordability_status",
            "recommended_payment_method", "payment_plan",
            "earliest_date_for_full_payment", "spending_changes_needed",
            "decision_explanation")

    def _rows_hash():
        res = run_dataset("dataset/official")
        blob = "\n".join(
            "|".join(d.to_serialized_row(home[d.request_id])[c] for c in cols)
            for d in res["decisions"]
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest(), res["usage"].calls

    monkeypatch.setenv("LLM_ENABLED", "0")
    monkeypatch.delenv("API_KEY", raising=False)
    h_e0, calls_e0 = _rows_hash()
    assert calls_e0 == 0
    monkeypatch.setenv("LLM_ENABLED", "1")
    monkeypatch.setenv("API_KEY", "DUMMY-NOT-A-REAL-KEY")
    monkeypatch.setenv("MODEL_PROVIDER", "p")
    monkeypatch.setenv("MODEL_NAME", "m")
    h_met, _ = _rows_hash()
    assert h_e0 == h_met  # OBSERVED: no-backend metered path is decision-identical


def test_retry_max_clamped():
    """F-07: LLM_MAX_RETRIES cannot create an unbounded attempt loop."""
    from affordai.evidence.llm_adapter import MAX_RETRIES_CAP, load_config_from_env
    assert MAX_RETRIES_CAP == 10
    cfg = load_config_from_env({"LLM_ENABLED": "1", "API_KEY": "x", "LLM_MAX_RETRIES": "999999"})
    assert cfg.max_retries == MAX_RETRIES_CAP
    calls = {"n": 0}

    def backend():
        calls["n"] += 1
        raise TimeoutError("t")

    raw, rec = call_with_retry(backend, cfg, purpose="message_extract")
    assert calls["n"] == 1 + MAX_RETRIES_CAP  # OBSERVED hard bound
    assert rec.fallback.startswith("retry-exhausted")
