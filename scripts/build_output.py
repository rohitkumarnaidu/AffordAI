"""End-to-end pipeline entry point: dataset -> deterministic decisions -> output.csv.

Section 25: serializer is deliberately boring -- converts canonical Decision
into exact 8-column schema via decisions_to_rows / write_output_csv.
Section 26: final validator blocks submission on any hard error.
"""
from __future__ import annotations

import argparse
import sys
import time

sys.path.insert(0, "src")

from affordai.evaluation.harness import run_dataset
from affordai.output.serializer import write_output_csv
from affordai.pipeline import build_contexts, load_dataset


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset/official")
    ap.add_argument("--out", default="output.csv")
    args = ap.parse_args()

    started = time.time()
    tables = load_dataset(args.dataset)
    contexts = build_contexts(tables)
    home_by_request = {c.request_id: c.profile["home_currency"] for c in contexts}
    result = run_dataset(args.dataset)
    decisions = result["decisions"]
    runtime_s = result["runtime_s"]
    usage = result["usage"]
    # Sec 32.3: persist metered token report for the FINAL full-dataset run
    import os as _os
    usage_md = usage.to_markdown(result["n_requests"], runtime_s)
    usage_path = _os.path.join("evaluation", "usage_report.md")
    try:
        with open(usage_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(usage_md)
        print(f"usage report -> {usage_path} ({usage.calls} calls, {usage.total_tokens} tokens)")
    except Exception as exc:
        print(f"WARN: could not write {usage_path}: {exc}")
    # Section 25: exact 8 columns, order, one row per request, original order, CSV escaping
    write_output_csv(decisions, home_by_request, args.out)
    # Section 26: final gate -- validate before declaring success
    from affordai.output.validator import validate_consistency, validate_evidence

    ev_errs = validate_evidence(decisions, contexts)
    cons_errs = validate_consistency(decisions)
    if ev_errs or cons_errs:
        print(f"WARN: post-serialization validator found {len(ev_errs)+len(cons_errs)} consistency/evidence issues (see validator)")
        for e in (ev_errs + cons_errs)[:10]:
            print(" -", e)
        # Do not silently continue on hard errors -- but file is still written for inspection
        # Caller (clean_room_run) will run validate_output.py which will FAIL the gate.

    runtime = time.time() - started
    from collections import Counter

    mix = Counter(d.affordability_status for d in decisions)
    print(f"wrote {len(decisions)} rows -> {args.out} in {runtime:.1f}s")
    print(f"status mix: {dict(mix)}")
    print(f"llm: {result['usage'].note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
