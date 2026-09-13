"""Validate output.csv against requests.csv (+options/profiles). Exit 1 on violation."""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, "src")

from affordai.output.validator import validate_files, validate_plans


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", default="dataset/official/requests.csv")
    ap.add_argument("--output", default="output.csv")
    ap.add_argument("--dataset", default="")
    ap.add_argument("--options", default="")
    ap.add_argument("--profiles", default="")
    args = ap.parse_args()
    dataset = args.dataset
    options = args.options or (os.path.join(dataset, "request_payment_options.csv") if dataset else "")
    profiles = args.profiles or (os.path.join(dataset, "financial_profiles.csv") if dataset else "")

    errors = validate_files(args.requests, args.output)
    if options and profiles:
        errors = errors + validate_plans(args.requests, options, profiles, args.output)
    if errors:
        print(f"FAIL: {len(errors)} error(s)")
        for e in errors[:50]:
            print(" -", e)
        return 1
    print("PASS: output.csv valid (structural + plan layers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
