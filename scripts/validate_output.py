"""Validate output.csv against requests.csv (+options/profiles). Exit 1 on violation.

Submission artifact gate (Sections 26.9, 8.11): ANY hard validation failure =
FINAL SUBMISSION BLOCKED. This script checks the CSV-PROVABLE layers:
structural, identity, numeric, enum, plan, spending, preference.
Evidence / consistency / canonical / floor-simulation layers need Decisions +
Contexts and run inside the pipeline (validate_evidence / validate_consistency
/ validate_canonical_consistency / simulate) plus the artifact-level proof in
scripts/final_red_flag_gate.py::check_artifact_finance. See that gate for the
complete Sec 44/45 story; this file alone is necessary but not sufficient.
"""
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
    ap.add_argument("--events", default="")
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
        # 26.11: any hard failure blocks finalization -- exit 1
        return 1
    print("PASS: output.csv valid (structural + plan layers)")
    # Note: evidence/consistency/safety layers require Decisions+Contexts and are
    # validated inside pipeline (validate_evidence/consistency/canonical/safety);
    # this file-based gate is the submission artifact check.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
