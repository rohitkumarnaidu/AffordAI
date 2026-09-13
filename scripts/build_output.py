"""End-to-end pipeline entry point: dataset -> deterministic decisions -> output.csv."""
from __future__ import annotations

import argparse
import csv
import sys
import time

sys.path.insert(0, "src")

from affordai.decision.decision import OUTPUT_COLUMNS
from affordai.evaluation.harness import run_dataset
from affordai.output.serializer import decisions_to_rows
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
    rows = decisions_to_rows(decisions, home_by_request)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    runtime = time.time() - started
    from collections import Counter

    mix = Counter(d.affordability_status for d in decisions)
    print(f"wrote {len(rows)} rows -> {args.out} in {runtime:.1f}s")
    print(f"status mix: {dict(mix)}")
    print(f"llm: {result['usage'].note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
