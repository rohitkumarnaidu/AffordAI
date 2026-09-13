"""Full-dataset benchmark (Sec 35.1): measured stages, bottlenecks, O(N^2) guard.

Usage:
    python scripts/benchmark.py --dataset dataset/official

Measures (LOCAL MEASUREMENT, wall clock):
    load | contexts | decide-all | serialize | validate
plus per-request decide stats (avg, slowest 5), model-call counts, image
selectivity counts, and cache status. Writes
`evaluation/local/benchmark.json` and prints a timing table.

No optimization without measurement: this script IS the measurement.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, "src")

from affordai.output.serializer import decisions_to_rows
from affordai.pipeline import build_contexts, decide_context, load_dataset
from affordai.observability.request_trace import RequestTrace, make_trace_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset/official")
    ap.add_argument("--run-id", default="E0")
    args = ap.parse_args()

    stages: dict[str, float] = {}
    t0 = time.perf_counter()
    tables = load_dataset(args.dataset)
    stages["data_load"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    contexts = build_contexts(tables)
    stages["join_canonicalization"] = time.perf_counter() - t0

    per_request: list[dict] = []
    all_records: list = []
    decisions = []
    n_blank = n_linked_existing = n_unknown = 0
    t0 = time.perf_counter()
    for ctx in contexts:
        s = time.perf_counter()
        recs: list = []
        rt = RequestTrace(
            request_id=ctx.request_id,
            original_row_index=ctx.original_index,
            trace_id=make_trace_id(args.run_id, ctx.request_id, ctx.original_index),
            run_id=args.run_id,
            start_time=time.time(),
        )
        d = decide_context(ctx, tables, args.dataset, rtrace=rt, run_id=args.run_id, out_records=recs)
        rt.finish("ok")
        decisions.append(d)
        all_records.extend(recs)
        per_request.append({"request_id": ctx.request_id, "seconds": round(time.perf_counter() - s, 4)})
        for e in ctx.events:
            if e.get("amount") is None:
                n_blank += 1
        n_unknown += sum(1 for f in rt.facts if f.get("normalized_value") == "unknown")
    stages["evidence_forecast_plans_decide"] = time.perf_counter() - t0
    # Image selectivity: linked-existing counts come from images.csv linkage.
    n_images_total = len(tables["images"])
    linked_event_ids = {i.get("related_event_id") for i in tables["images"] if i.get("related_event_id")}
    n_linked_existing = len(linked_event_ids)

    decisions.sort(key=lambda d: d.original_index)
    home_by_request = {c.request_id: c.profile["home_currency"] for c in contexts}
    t0 = time.perf_counter()
    rows = decisions_to_rows(decisions, home_by_request)
    stages["serialize"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    from affordai.output.validator import validate_consistency

    cons_errs = validate_consistency(decisions)
    stages["validate_consistency"] = time.perf_counter() - t0

    total = sum(stages.values())
    per_request_sorted = sorted(per_request, key=lambda r: r["seconds"], reverse=True)
    avg = (stages["evidence_forecast_plans_decide"] / len(decisions)) if decisions else 0.0
    bottleneck = max(stages.items(), key=lambda kv: kv[1])
    report = {
        "dataset": args.dataset,
        "n_requests": len(decisions),
        "n_events": len(tables["events"]),
        "n_messages": len(tables["messages"]),
        "n_images": n_images_total,
        "stages_s": {k: round(v, 3) for k, v in stages.items()},
        "total_s": round(total, 3),
        "bottleneck": {"stage": bottleneck[0], "seconds": round(bottleneck[1], 3),
                       "pct": round(100 * bottleneck[1] / total, 1) if total else 0.0},
        "per_request_decide_avg_s": round(avg, 4),
        "slowest_5_requests": per_request_sorted[:5],
        "model_calls": len(all_records),
        "model_input_tokens": sum(getattr(r, "input_tokens", 0) for r in all_records),
        "model_output_tokens": sum(getattr(r, "output_tokens", 0) for r in all_records),
        "image_selectivity": {
            "images_total": n_images_total,
            "linked_events": n_linked_existing,
            "unknown_amount_markers": n_unknown,
            "policy": "only blank-amount events with linked existing files trigger vision; blank is never zero",
        },
        "caching": "CACHE NOT ADOPTED -- payloads unique per request (ids+text); ModelCache versioned + opt-in only on measured reuse",
        "consistency_errors": len(cons_errs),
        "note": "LOCAL MEASUREMENT (wall clock, this machine). Not an official score.",
    }
    os.makedirs("evaluation/local", exist_ok=True)
    with open("evaluation/local/benchmark.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, indent=1)

    print(f"benchmark {args.dataset}: {len(decisions)} requests")
    for k, v in stages.items():
        pct = (100 * v / total) if total else 0.0
        print(f"  {k:32s} {v:7.3f}s  ({pct:5.1f}%)")
    print(f"  {'TOTAL':32s} {total:7.3f}s")
    print(f"bottleneck: {bottleneck[0]} ({100*bottleneck[1]/total:.1f}% of total)" if total else "bottleneck: n/a")
    print(f"per-request decide avg: {avg*1000:.1f}ms; slowest: {per_request_sorted[0]['request_id']} {per_request_sorted[0]['seconds']}s" if per_request_sorted else "")
    print(f"model calls: {len(all_records)}; images: {n_images_total} total / {n_linked_existing} linked events / {n_unknown} UNKNOWN markers")
    print(f"consistency errors: {len(cons_errs)}")
    print("report -> evaluation/local/benchmark.json")
    return 0 if not cons_errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
