"""Final red-flag gate (Checklist Sec 44): executable, runnable, blocking.

Usage:  python scripts/final_red_flag_gate.py [--dataset dataset/official]

Every check prints ``<name> ............... PASS|FAIL|SKIP`` with evidence.
ANY FAIL -> exit 1 (NO-GO). No warnings silently pass; SKIP is allowed only
where the check genuinely cannot apply, and is listed loudly.

Layering (honest): file-level checks reuse src/affordai/output/validator.py;
artifact-level financial proof REBUILDS each request's state through the REAL
pipeline stages (load -> build_contexts -> _collect_evidence ->
confirmed_series -> amends -> build_flows -> build_state) with LLM disabled,
then re-derives amount_safe_to_pay / earliest_date from scratch and
re-simulates the CSV plan. The replay-hash check binds the committed
output.csv to this exact code. LLM-boundary and attack checks execute real
probes (static scan + adversarial/security test subset). Secrets delegate to
scripts/scan_secrets.py. Clean-room delegates to scripts/clean_room_run.py.
Full regression runs the whole pytest suite.

Side effects: reads dataset + output.csv; runs subprocesses (pytest,
scan, clean-room). Restores evaluation/usage_report.md bytes afterwards
(build_output rewrites it with runtime jitter only).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

LINES: list[str] = []
FAILURES = 0


def report(name: str, status: str, detail: str = "") -> None:
    global FAILURES
    dots = "." * max(2, 30 - len(name))
    line = f"{name} {dots} {status}" + (f" ({detail})" if detail else "")
    print(line, flush=True)
    LINES.append(line)
    if status == "FAIL":
        FAILURES += 1


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def _verdict_line(output: str) -> str:
    lines = (output or "").strip().splitlines()
    for line in reversed(lines):
        if "passed" in line or "failed" in line or "error" in line.lower():
            return line.strip()[:160]
    return lines[-1].strip()[:160] if lines else "no output"


def check_file_layers(dataset: str) -> bool:
    """Structural + plan layers via the real validator (row order, dup/missing,
    amounts, totals, deadlines, installments, spending, methods, prefs)."""
    from affordai.output.validator import validate_files, validate_plans

    req = str(ROOT / dataset / "requests.csv")
    out = str(ROOT / "output.csv")
    errors = validate_files(req, out)
    opt = str(ROOT / dataset / "request_payment_options.csv")
    prof = str(ROOT / dataset / "financial_profiles.csv")
    errors += validate_plans(req, opt, prof, out)
    if errors:
        report("file_layers", "FAIL", f"{len(errors)} errors; first: {errors[0][:160]}")
        return False
    report("file_layers", "PASS", "validate_files+validate_plans 0 errors")
    return True


def _parse_plan(plan: str) -> list:
    if plan == "none":
        return []
    legs = []
    for leg in plan.split("|"):
        day_s, amt_s = leg.split(":")
        legs.append((date.fromisoformat(day_s), Decimal(amt_s)))
    return legs


def _parse_changes(changes: str, events_by_id: dict, home: str, rates) -> dict:
    from affordai.finance.money import parse_amount
    from affordai.finance.spending_changes import _home_cap

    out: dict = {}
    if changes == "none":
        return out
    for part in changes.split("|"):
        segs = part.split(":")
        if segs[0] == "stop":
            out[segs[1]] = None
        else:
            _, eid, amt_s = segs
            raw = parse_amount(amt_s)
            row = events_by_id.get(eid, {})
            cap = _home_cap(raw, str(row.get("currency") or home), home,
                            row.get("settlement_date"), rates)
            out[eid] = cap if cap is not None else raw
    return out


def check_artifact_finance(dataset: str) -> bool:
    """Re-derive safe/earliest per request and re-simulate the CSV plan."""
    from affordai.evidence import conflict_resolver
    from affordai.evidence.llm_adapter import LlmConfig
    from affordai.finance.forecast import earliest_full_date, max_safe_today, simulate
    from affordai.finance.money import parse_amount
    from affordai.finance.state import build as build_state
    from affordai.finance.timeline import build_flows
    from affordai.evidence.message_income import confirmed_series
    from affordai.pipeline import _collect_evidence, build_contexts, load_dataset

    tables = load_dataset(str(ROOT / dataset))
    contexts = build_contexts(tables)
    cfg = LlmConfig(enabled=False)
    media = str(ROOT / dataset / "media" / "images")
    rows = {r["request_id"]: r for r in
            csv.DictReader(open(ROOT / "output.csv", newline="", encoding="utf-8"))}
    bad: list[str] = []
    checked = 0
    for ctx in contexts:
        rid = ctx.request_id
        csv_row = rows.get(rid)
        if csv_row is None:
            bad.append(f"{rid}: missing from output.csv")
            continue
        registry, _, _, _ = _collect_evidence(ctx, media, cfg, None)
        facts = registry.facts_for(rid)
        cancelled = conflict_resolver.cancelled_event_ids(facts)
        amend_amounts: dict = {}
        for eid, raw in conflict_resolver.amended_amounts(facts).items():
            try:
                v = parse_amount(raw)
            except ValueError:
                continue
            if v is not None and v > 0:
                amend_amounts[eid] = v
        amend_dates = {}
        for eid, raw in conflict_resolver.amended_dates(facts).items():
            try:
                from datetime import datetime as _dt
                amend_dates[eid] = _dt.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                continue
        extra = []
        for m in sorted(ctx.messages, key=lambda m: (str(m["sent_at"]), m["message_id"])):
            try:
                series, _ = confirmed_series(ctx, m, ctx.profile["home_currency"], tables["rates"])
            except Exception:
                continue
            extra.extend((d, a, m["message_id"]) for d, a in series)
        flows, unknowns, notes = build_flows(ctx, tables["rates"], cancelled,
                                             amend_amounts, amend_dates, extra)
        state = build_state(ctx, flows, unknowns, notes)
        home = ctx.profile["home_currency"]
        safe = max_safe_today(state)
        earliest = earliest_full_date(state)
        csv_safe = Decimal(csv_row["amount_safe_to_pay"])
        csv_earliest = csv_row["earliest_date_for_full_payment"].strip()
        if csv_safe != safe:
            bad.append(f"{rid}: safe {csv_safe} != rederived {safe}")
            continue
        exp_earliest = earliest.isoformat() if earliest else ""
        if csv_earliest != exp_earliest:
            bad.append(f"{rid}: earliest {csv_earliest!r} != rederived {exp_earliest!r}")
            continue
        method = csv_row["recommended_payment_method"]
        if method != "not_recommended":
            legs = _parse_plan(csv_row["payment_plan"])
            events_by_id = {e["event_id"]: e for e in ctx.events}
            changes = _parse_changes(csv_row["spending_changes_needed"], events_by_id,
                                     home, tables["rates"])
            if not simulate(state, legs, changes).ok:
                bad.append(f"{rid}: CSV plan fails floor re-simulation")
                continue
        else:
            # not_affordable/not_recommended with safe > 0 is VALID: partial
            # capacity can exist today while the full amount is never safe
            # (partial needs earliest <= deadline + acceptance; without those
            # the method is not_recommended). earliest=="" already matched the
            # rederived None above; bounds are proven by file_layers.
            requested = ctx.request.get("requested_amount")
            if not (Decimal(0) <= csv_safe <= requested):
                bad.append(f"{rid}: not_recommended safe {csv_safe} out of [0, requested]")
                continue
        checked += 1
    if bad:
        report("artifact_finance", "FAIL", f"{len(bad)} rows; first: {bad[0][:160]}")
        return False
    report("artifact_finance", "PASS", f"{checked}/250 safe+earliest rederived, plans re-simulated")
    return True


def check_evidence_consistency() -> bool:
    from affordai.evidence.llm_adapter import LlmConfig
    from affordai.output.validator import (validate_canonical_consistency,
                                           validate_consistency, validate_evidence)
    from affordai.pipeline import build_contexts, load_dataset, run

    tables = load_dataset(str(ROOT / "dataset" / "official"))
    contexts = build_contexts(tables)
    decisions, _ = run(str(ROOT / "dataset" / "official"),
                       llm_config=LlmConfig(enabled=False), run_id="GATE")
    errs = validate_evidence(decisions, contexts) + validate_consistency(decisions)
    errs += validate_canonical_consistency(decisions, str(ROOT / "output.csv"))
    if errs:
        report("evidence_consistency", "FAIL", f"{len(errs)} errors; first: {errs[0][:160]}")
        return False
    report("evidence_consistency", "PASS", "evidence+consistency+canonical 0 errors")
    return True


def check_replay_hash() -> bool:
    import io as _io
    from affordai.evidence.llm_adapter import LlmConfig
    from affordai.output.serializer import decisions_to_rows
    from affordai.pipeline import build_contexts, load_dataset, run

    ds = str(ROOT / "dataset" / "official")
    decisions, info = run(ds, llm_config=LlmConfig(enabled=False), run_id="GATE")
    tables = load_dataset(ds)
    homes = {c.request_id: c.profile["home_currency"] for c in build_contexts(tables)}
    rows = decisions_to_rows(decisions, homes)
    buf = _io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n",
                       quoting=csv.QUOTE_MINIMAL)
    w.writeheader()
    w.writerows(rows)
    disk = (ROOT / "output.csv").read_bytes()
    if buf.getvalue().encode() != disk:
        report("replay_hash", "FAIL", "LLM-disabled rerun differs from output.csv")
        return False
    report("replay_hash", "PASS",
           f"sha {hashlib.sha256(disk).hexdigest()[:12]} reproduced, {info['n_fallbacks']} fallbacks")
    return True


def check_llm_boundary() -> bool:
    import pathlib
    tokens = ("propose_facts(", "llm_adapter", "openai", "anthropic",
              "import random", "random.", "import time", "time.time(",
              "datetime.now(", "date.today(", "threading", "multiprocessing")
    mods = sorted((ROOT / "src" / "affordai" / "finance").glob("*.py"))
    mods += sorted((ROOT / "src" / "affordai" / "decision").glob("*.py"))
    hits = []
    for p in mods:
        if p.name == "__init__.py":
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if not s or s[0] in "#'\"`":
                continue
            for t in tokens:
                if t in line:
                    hits.append(f"{p.name}:{i}:{t}")
    pipe = (ROOT / "src" / "affordai" / "pipeline.py").read_text(encoding="utf-8")
    if pipe.count("propose_facts(") != 2:
        hits.append("pipeline.py: propose_facts call sites != 2")
    if hits:
        report("llm_boundary", "FAIL", "; ".join(hits[:4]))
        return False
    report("llm_boundary", "PASS", "core clean; 2 gated LLM call sites in pipeline")
    return True


def check_attacks() -> bool:
    r = _run([sys.executable, "-m", "pytest", "tests/adversarial", "tests/security",
              "tests/regression/test_sections_43_52_audits.py", "-q", "-p", "no:warnings"], 600)
    verdict = _verdict_line(r.stdout + r.stderr)
    if r.returncode != 0:
        report("attacks", "FAIL", verdict[:160])
        return False
    report("attacks", "PASS", verdict[:160])
    return True


def check_secrets() -> bool:
    r = _run([sys.executable, "scripts/scan_secrets.py"], 300)
    verdict = _verdict_line(r.stdout + r.stderr)
    if r.returncode != 0:
        report("secrets", "FAIL", verdict[:160])
        return False
    report("secrets", "PASS", verdict[:160])
    return True


def check_usage_and_transcript() -> bool:
    ok = True
    usage = (ROOT / "evaluation" / "usage_report.md").read_text(encoding="utf-8")
    need = ["Model provider", "Model name", "Model calls", "Input tokens",
            "Output tokens", "Total tokens", "Average tokens/request",
            "Estimated total cost", "Estimated cost/request"]
    missing = [k for k in need if k not in usage]
    if missing:
        report("usage_report", "FAIL", f"missing fields: {missing}")
        ok = False
    else:
        note = "costs UNKNOWN (declared)" if "UNKNOWN" in usage else "costs stated"
        report("usage_report", "PASS", note)
    log = ROOT / "log.txt"
    if not log.is_file() or log.stat().st_size == 0:
        report("transcript", "FAIL", "log.txt missing/empty")
        ok = False
    else:
        blob = log.read_text(encoding="utf-8", errors="replace")
        if "SESSION START" not in blob or "tool=opencode" not in blob:
            report("transcript", "FAIL", "missing SESSION START / tool identity")
            ok = False
        else:
            report("transcript", "PASS", f"{log.stat().st_size // 1024}KB, tool identity present")
    return ok


def check_clean_room(dataset: str) -> bool:
    usage_path = ROOT / "evaluation" / "usage_report.md"
    before = usage_path.read_bytes() if usage_path.is_file() else None
    try:
        r = _run([sys.executable, "scripts/clean_room_run.py", "--dataset", dataset], 1500)
    finally:
        if before is not None:
            usage_path.write_bytes(before)  # restore runtime-jitter bytes
    verdict = _verdict_line(r.stdout + r.stderr)
    if r.returncode != 0:
        report("clean_room", "FAIL", verdict[:160])
        return False
    report("clean_room", "PASS", verdict[:160])
    return True


def check_regression() -> bool:
    r = _run([sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:warnings"], 900)
    verdict = _verdict_line(r.stdout + r.stderr)
    if r.returncode != 0:
        report("regression", "FAIL", verdict[:160])
        return False
    report("regression", "PASS", verdict[:160])
    return True


def check_identity(dataset: str) -> bool:
    req = list(csv.DictReader(open(ROOT / dataset / "requests.csv", newline="", encoding="utf-8-sig")))
    out = list(csv.DictReader(open(ROOT / "output.csv", newline="", encoding="utf-8-sig")))
    if len(req) != len(out):
        report("row_identity", "FAIL", f"requests {len(req)} != output {len(out)}")
        return False
    rids = [r["request_id"] for r in req]
    oids = [r["request_id"] for r in out]
    if rids != oids:
        report("row_identity", "FAIL", "order/ID mismatch")
        return False
    if len(set(oids)) != len(oids):
        report("row_identity", "FAIL", "duplicate request_id")
        return False
    report("row_identity", "PASS", f"{len(out)} rows, order+IDs exact")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset/official")
    args = ap.parse_args()
    print("FINAL RED-FLAG GATE (Sec 44) -- one FAIL = NO-GO")
    try:
        check_identity(args.dataset)
        check_file_layers(args.dataset)
        check_replay_hash()
        check_artifact_finance(args.dataset)
        check_evidence_consistency()
        check_llm_boundary()
        check_attacks()
        check_secrets()
        check_usage_and_transcript()
        check_clean_room(args.dataset)
        check_regression()
    except Exception as exc:  # a crashed gate is a failed gate
        report("gate_crash", "FAIL", f"{type(exc).__name__}: {exc}"[:160])
    print(f"RED-FLAG GATE: {'NO-GO (' + str(FAILURES) + ' FAIL)' if FAILURES else 'ALL CLEAR'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
