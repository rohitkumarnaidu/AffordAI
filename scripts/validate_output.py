"""Validate output.csv against requests.csv. Exit 1 on any violation."""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "src")

from affordai.output.validator import validate_files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", default="dataset/official/requests.csv")
    ap.add_argument("--output", default="output.csv")
    args = ap.parse_args()
    errors = validate_files(args.requests, args.output)
    if errors:
        print(f"FAIL: {len(errors)} error(s)")
        for e in errors[:50]:
            print(" -", e)
        return 1
    print("PASS: output.csv valid (structural layer)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
