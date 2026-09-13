"""Full-dataset evaluation report (Section 27.4): baseline + final + deltas.

Usage:
    python scripts/eval_report.py --dataset dataset/official --tag baseline
    python scripts/eval_report.py --dataset dataset/official --tag final

Writes evaluation/reports/eval_<tag>.json + eval_<tag>.md.
Compares final vs baseline with honest deltas (regressions reported as-is).
All figures LOCAL MEASUREMENT; OFFICIAL score UNKNOWN.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time

sys.path.insert(0, "src")

from affordai.evaluation.harness import run_dataset  # noqa: E402
from affordai.evaluation.metrics import OFFICIAL_SCORE_NOTE, categorize_errors, full_dataset_metrics  # noqa: E402
from affordai.pipeline import build_contexts, load_dataset  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset/official")
    ap.add_argument("--tag", default="final")
    ap.add_argument("--out", default="evaluation/reports")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    started = time.time()
    result = run_dataset(args.dataset)
    decisions = sorted(result["decisions"], key=lambda d: d.original_index)
    tables = load_dataset(args.dataset)
    contexts = build_contexts(tables)
    full = full_dataset_metrics(decisions, contexts, args.dataset)
    cats = categorize_errors(full)
    usage = result["usage"]
    report = {
        "tag": args.tag,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dataset": args.dataset,
        "version": "E7-production (all components, deterministic, LLM off)",
        "n_requests": result["n_requests"],
        "n_fallbacks": result.get("n_fallbacks", 0) if isinstance(result, dict) else 0,
        "runtime_s": round(time.time() - started, 2),
        "metrics": full,
        "failure_categories": cats,
        "tokens": {
            "provider": usage.provider,
            "model": usage.model,
            "calls": usage.calls,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "note": usage.note,
        },
        "result_kind": "LOCAL MEASUREMENT",
        "official_score": "UNKNOWN",
        "official_note": OFFICIAL_SCORE_NOTE,
    }
    base_path = os.path.join(args.out, "eval_baseline.json")
    if args.tag == "final" and os.path.exists(base_path):
        base = json.load(open(base_path, encoding="utf-8"))
        bm, fm = base["metrics"], full
        report["deltas_vs_baseline"] = {
            "structural_errors": fm["structural_validity"]["errors"] - bm["structural_validity"]["errors"],
            "plan_errors": fm["plan_correctness"]["errors"] - bm["plan_correctness"]["errors"],
            "evidence_errors": fm["evidence_validity"]["errors"] - bm["evidence_validity"]["errors"],
            "explanation_invalid": len(fm["explanation_consistency"]["invalid_ids"]) - len(bm["explanation_consistency"]["invalid_ids"]),
            "note": "negative = fewer errors (improvement); positive = regression, reported honestly, never hidden",
        }
        report["baseline_timestamp"] = base.get("timestamp", "?")
    with open(os.path.join(args.out, f"eval_{args.tag}.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    with open(os.path.join(args.out, f"eval_{args.tag}.md"), "w", encoding="utf-8") as fh:
        fh.write(_markdown(report))
    print(
        f"eval_{args.tag}: n={report['n_requests']} struct_err={full['structural_validity']['errors']} "
        f"plan_err={full['plan_correctness']['errors']} ev_err={full['evidence_validity']['errors']} "
        f"expl_rate={full['explanation_consistency']['rate']:.3f} runtime={report['runtime_s']}s",
        flush=True,
    )
    return 0


def _markdown(r: dict) -> str:
    m = r["metrics"]
    lines = [
        f"# Evaluation Report -- {r['tag']} (LOCAL MEASUREMENT)",
        "",
        f"- timestamp: {r['timestamp']}",
        f"- dataset: {r['dataset']} (n={r['n_requests']}, fallbacks={r['n_fallbacks']})",
        f"- version: {r['version']}",
        f"- runtime: {r['runtime_s']}s",
        f"- OFFICIAL score: {r['official_score']} -- {r['official_note']}",
        "",
        "## Metrics (27.2)",
        "",
        f"- structural_validity: errors={m['structural_validity']['errors']} pass={m['structural_validity']['pass']}",
        f"- numerical_correctness: bounds_violations={m['numerical_correctness']['bounds_violations']} pass={m['numerical_correctness']['pass']}",
        f"- plan_correctness: errors={m['plan_correctness']['errors']} pass={m['plan_correctness']['pass']}",
        f"- evidence_validity: errors={m['evidence_validity']['errors']} pass={m['evidence_validity']['pass']}",
        f"- explanation_consistency: rate={m['explanation_consistency']['rate']:.3f} invalid={m['explanation_consistency']['invalid_ids'][:10]}",
        f"- decision_consistency: errors={m['decision_consistency']['errors']} pass={m['decision_consistency']['pass']}",
        f"- tokens: calls={r['tokens']['calls']} total={r['tokens']['total_tokens']} ({r['tokens']['note']})",
        "",
        "## Failure categories (27.4)",
        "",
    ]
    for cat, count in r["failure_categories"].items():
        lines.append(f"- {cat}: {count}")
    if "deltas_vs_baseline" in r:
        d = r["deltas_vs_baseline"]
        lines += [
            "",
            f"## Deltas vs baseline ({r.get('baseline_timestamp', '?')})",
            "",
            f"- structural_errors delta: {d['structural_errors']}",
            f"- plan_errors delta: {d['plan_errors']}",
            f"- evidence_errors delta: {d['evidence_errors']}",
            f"- explanation_invalid delta: {d['explanation_invalid']}",
            f"- {d['note']}",
        ]
    lines += [
        "",
        "## Remaining failures",
        "",
        (
            "None -- all validator layers green on the full dataset."
            if all(
                [
                    m["structural_validity"]["pass"],
                    m["numerical_correctness"]["pass"],
                    m["plan_correctness"]["pass"],
                    m["evidence_validity"]["pass"],
                    m["explanation_consistency"]["pass"],
                    m["decision_consistency"]["pass"],
                ]
            )
            else "See error samples in eval JSON."
        ),
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
