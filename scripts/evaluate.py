"""Local proxy evaluation (NOT official score): pipeline on sample rows + metrics."""
from __future__ import annotations

import argparse
import json
import sys
import time

sys.path.insert(0, "src")

from affordai.evaluation.harness import run_dataset
from affordai.evaluation.metrics import compare
from affordai.ingestion import requests as ingest_requests
from affordai.pipeline import build_contexts, decide_context, load_dataset


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset/official")
    args = ap.parse_args()

    started = time.time()
    tables = load_dataset(args.dataset)
    sample_rows = ingest_requests.load(f"{args.dataset}/sample_requests.csv")
    tables["requests"] = sample_rows
    contexts = build_contexts(tables)
    decisions = [decide_context(c, tables, args.dataset) for c in contexts]
    metrics = compare(decisions, f"{args.dataset}/sample_requests.csv")
    metrics["runtime_s"] = round(time.time() - started, 1)
    metrics["n_sample"] = len(decisions)
    print(json.dumps(metrics, indent=1))

    from affordai.evaluation import regression as regression_mod

    import os

    os.makedirs("evaluation/local", exist_ok=True)  # gitignored scratch space
    snap_path = "evaluation/local/last_snapshot.json"
    new_snap = regression_mod.snapshot(decisions)
    try:
        with open(snap_path, encoding="utf-8") as fh:
            old_snap = json.load(fh)
        drift = regression_mod.diff(old_snap, new_snap)
        print(f"regression drift vs {snap_path}: {len(drift)} rows: {drift[:10]}")
    except OSError:
        print(f"no prior snapshot at {snap_path}; writing baseline")
    regression_mod.save(decisions, snap_path)
    print(f"snapshot saved -> {snap_path}")

    full = run_dataset(args.dataset)
    print(f"full run: {full['n_requests']} rows in {full['runtime_s']:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
