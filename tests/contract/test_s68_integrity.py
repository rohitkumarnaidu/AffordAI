"""Sections 6-8 integrity: joins, canonical context, evidence (no-duplicate complement).

Complements test_p0_hardening.py (conflict/protected/preference/blank/image)
and test_phase45_contract.py (dataset-level FKs) with join-level guarantees:
wrong-user/request rejection, dedupe, isolation, deterministic ordering,
provenance round-trip, cross-kind conflicts, claim support, output alignment,
parallel-order stability. All names prefixed test_s68_ (unique, no collisions).
"""
import copy
import sys
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, "src")

from affordai.evidence import conflict_resolver
from affordai.evidence.evidence_registry import Evidence, EvidenceRegistry
from affordai.pipeline import build_contexts, load_dataset


def _tables():
    return load_dataset("dataset/official")


def test_s68_wrong_user_message_rejected_at_join():
    tables = _tables()
    tables2 = copy.deepcopy(tables)
    mal = {
        "message_id": "message_mal_s68",
        "user_id": "user_27",
        "request_id": "request_26",
        "related_event_id": None,
        "sent_at": datetime(2025, 1, 1),
        "source_type": "employer",
        "message_text": "cancel this",
    }
    tables2["messages"].append(mal)
    ctxs = build_contexts(tables2)
    ctx26 = next(c for c in ctxs if c.request_id == "request_26")
    assert not any(m["message_id"] == "message_mal_s68" for m in ctx26.messages)
    assert any(i.code == "WRONG_USER" for i in ctx26.join_issues)


def test_s68_wrong_user_image_rejected_at_join():
    tables = _tables()
    tables2 = copy.deepcopy(tables)
    mal = {"image_id": "image_mal_s68", "user_id": "user_99", "request_id": "request_26", "related_event_id": None}
    tables2["images"].append(mal)
    ctxs = build_contexts(tables2)
    ctx26 = next(c for c in ctxs if c.request_id == "request_26")
    assert not any(i["image_id"] == "image_mal_s68" for i in ctx26.images)
    assert any(i.code == "WRONG_USER" for i in ctx26.join_issues)


def test_s68_duplicate_event_deduped_not_doubled():
    tables = _tables()
    ev = next(e for e in tables["events"] if e["user_id"] == "user_26")
    tables2 = copy.deepcopy(tables)
    tables2["events"].append(copy.deepcopy(ev))
    ctxs = build_contexts(tables2)
    c26 = next(c for c in ctxs if c.user_id == "user_26")
    assert sum(1 for e in c26.events if e["event_id"] == ev["event_id"]) == 1
    assert any(i.code == "DUPLICATE_JOIN" for i in c26.join_issues)


def test_s68_context_isolation_no_shared_mutation():
    tables = copy.deepcopy(_tables())
    # synthetic second request for same user to test sharing
    req = copy.deepcopy(tables["requests"][0])
    req["request_id"] = "request_s68_dup"
    req["original_index"] = 9999
    tables["requests"].append(req)
    ctxs = build_contexts(tables)
    c26 = next(c for c in ctxs if c.request_id == "request_26")
    c999 = next(c for c in ctxs if c.request_id == "request_s68_dup")
    assert c26.events is not c999.events
    assert c26.profile is not c999.profile
    if c26.events:
        orig = c26.events[0]["amount"]
        c26.events[0]["amount"] = Decimal("999999")
        assert c999.events[0]["amount"] != Decimal("999999")
        assert not any(e.get("amount") == Decimal("999999") for e in tables["events"])
        c26.events[0]["amount"] = orig


def test_s68_deterministic_ordering():
    tables = _tables()
    ctxs = build_contexts(tables)
    for c in ctxs[:5]:
        ekeys = [(str(e.get("settlement_date")), e.get("event_id", "")) for e in c.events]
        assert ekeys == sorted(ekeys)
        mkeys = [(str(m.get("sent_at")), m.get("message_id", "")) for m in c.messages]
        assert mkeys == sorted(mkeys)
        ikeys = [i.get("image_id", "") for i in c.images]
        assert ikeys == sorted(ikeys)
        okeys = [o.get("payment_option_id", "") for o in c.payment_options]
        assert okeys == sorted(okeys)


def test_s68_identity_validation_detects_tamper():
    tables = _tables()
    ctxs = build_contexts(tables)
    c = ctxs[0]
    assert c.validate_identity() == []
    c.request_id = "tampered"
    assert len(c.validate_identity()) > 0


def test_s68_relationships_clean_on_real_data():
    tables = _tables()
    ctxs = build_contexts(tables)
    # Real dataset has 0 true cross-user leaks; live re-check must be error-free
    for c in ctxs:
        errs = [i for i in c.validate_relationships() if i.severity == "error"]
        assert errs == [], (c.request_id, errs[:2])


def test_s68_provenance_round_trip():
    ev = Evidence(
        source_type="message",
        source_id="message_01",
        request_id="request_26",
        user_id="user_26",
        event_id=None,
        message_id="message_01",
        kind="confirm",
        raw_value="confirmed salary",
        normalized_value="confirmed",
        confidence=Decimal("1.0"),
        method="deterministic",
        sent_at="2025-01-01T00:00:00",
    )
    ev.extraction_method = ev.method
    prov = ev.provenance()
    assert prov["source_id"] == "message_01"
    assert prov["raw_value"] == "confirmed salary"
    assert prov["normalized_value"] == "confirmed"
    assert prov["extraction_method"] == "deterministic"
    assert prov["sent_at"] == "2025-01-01T00:00:00"


def test_s68_registry_rejects_bad_ids_and_confidence():
    reg = EvidenceRegistry(valid_event_ids={"e1"}, valid_message_ids={"m1"}, valid_image_ids={"img1"})
    reg.add(Evidence("message", "m1", "r1", "u1", event_id="e1", kind="cancel"), "r1", "u1")
    assert len(reg) == 1
    for bad in [
        Evidence("message", "m2", "r1", "u1", event_id="e_nope", kind="cancel"),
        Evidence("message", "m2", "r2", "u1", event_id="e1", kind="cancel"),
        Evidence("message", "m2", "r1", "u2", event_id="e1", kind="cancel"),
        Evidence("bogus", "m2", "r1", "u1", event_id="e1", kind="cancel"),
        Evidence("message", "m2", "r1", "u1", event_id="e1", kind="approve_anyway"),
    ]:
        try:
            reg.add(bad, "r1", "u1")
        except Exception:
            pass
        else:
            raise AssertionError(f"accepted {bad}")
    try:
        reg.add(Evidence("message", "m9", "r1", "u1", event_id="e1", kind="cancel", confidence=Decimal("1.5")), "r1", "u1")
    except Exception:
        pass
    else:
        raise AssertionError("bad confidence accepted")
    assert len(reg) == 1
    assert len(reg.rejected()) >= 5
    assert reg.validate_provenance() == []


def test_s68_cross_kind_conflict_represented():
    def _ev(kind, sid, sent):
        return Evidence("message", sid, "r1", "u1", event_id="e1", message_id=sid, kind=kind,
                         raw_value="x", normalized_value="100" if kind == "amend_amount" else "2025-02-01",
                         confidence=Decimal("1.0"), method="deterministic", sent_at=sent)
    cancel = _ev("cancel", "m1", "2025-01-01T10:00:00")
    amend = _ev("amend_amount", "m2", "2025-01-05T10:00:00")
    conflicts = conflict_resolver.detect_conflicts([cancel, amend])
    assert len(conflicts) == 1
    assert conflicts[0].event_id == "e1"
    assert conflicts[0].winning_fact.kind == "cancel"
    assert "rule1" in conflicts[0].rule


def test_s68_claim_support_validation():
    reg = EvidenceRegistry()
    reg.add(Evidence("message", "m1", "r1", "u1", event_id=None, kind="confirm"), "r1", "u1")
    assert reg.validate_claim_support({"confirm"}) == []
    missing = reg.validate_claim_support({"cancel"})
    assert len(missing) == 1 and "cancel" in missing[0]


def test_s68_output_alignment_and_parallel_stability():
    import concurrent.futures

    tables = _tables()
    ctxs = build_contexts(tables)
    assert len(ctxs) == 250
    assert len({c.request_id for c in ctxs}) == 250
    assert len({c.original_index for c in ctxs}) == 250

    def _build_once(_):
        t = load_dataset("dataset/official")
        return [(c.request_id, c.original_index) for c in build_contexts(t)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        runs = list(ex.map(_build_once, range(4)))
    base = sorted(runs[0])
    for r in runs[1:]:
        assert sorted(r) == base
    # original_index reconstructs input order regardless of thread completion order
    req_ids = [r["request_id"] for r in tables["requests"]]
    by_idx = sorted(ctxs, key=lambda c: c.original_index)
    assert [c.request_id for c in by_idx] == req_ids
