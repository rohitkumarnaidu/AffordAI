"""Interview debugging CLI (Sec 33.2): reconstruct ONE request's full chain.

Usage:
    python scripts/trace_request.py --request request_26
    python scripts/trace_request.py --request request_26 --out evaluation/local/trace_request_26.json

Prints the secret-safe JSON RequestTrace:
    REQUEST -> EVIDENCE -> EXTRACTED FACTS -> FINANCIAL STATE -> FORECAST
    -> CANDIDATE PLANS -> REJECTIONS -> SELECTED PLAN -> FINAL DECISION
    -> OUTPUT ROW
No dashboard; structured JSON is the debugging interface.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

sys.path.insert(0, "src")

from affordai.observability.request_trace import RequestTrace, make_trace_id
from affordai.pipeline import build_contexts, decide_context, load_dataset


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset/official")
    ap.add_argument("--request", required=True, help="request_id to trace")
    ap.add_argument("--out", default="")
    ap.add_argument("--run-id", default="E0")
    args = ap.parse_args()

    tables = load_dataset(args.dataset)
    contexts = build_contexts(tables)
    ordered = sorted(contexts, key=lambda c: c.original_index)
    row_index = next((i for i, c in enumerate(ordered) if c.request_id == args.request), None)
    if row_index is None:
        print(f"unknown request_id {args.request!r} (250 requests in dataset/official)")
        return 2
    ctx = ordered[row_index]
    rt = RequestTrace(
        request_id=ctx.request_id,
        original_row_index=ctx.original_index,
        trace_id=make_trace_id(args.run_id, ctx.request_id, ctx.original_index),
        run_id=args.run_id,
        start_time=time.time(),
    )
    decision = decide_context(ctx, tables, args.dataset, rtrace=rt, run_id=args.run_id)
    rt.finish("ok" if rt.status == "pending" else rt.status)
    rt.output_row = {
        "output_row_index": row_index,
        "request_id": decision.request_id,
        "validation_status": "decision-invariant-pass; csv-validator-see-scripts/validate_output.py",
    }
    blob = rt.to_json()
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(blob + "\n")
        print(f"trace {args.request} -> {args.out} ({decision.affordability_status}/{decision.recommended_payment_method})")
    else:
        print(blob)
    # One-line human chain summary (stderr-safe: stdout stays pure JSON when no --out)
    summary = {
        "request_id": rt.request_id,
        "trace_id": rt.trace_id,
        "status": decision.affordability_status,
        "method": decision.recommended_payment_method,
        "n_facts": len(rt.facts),
        "n_candidates": len(rt.candidates),
        "n_rejected": len(rt.rejected_plans),
        "selected": rt.selected_plan,
    }
    if args.out:
        print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
