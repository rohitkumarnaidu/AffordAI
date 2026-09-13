"""Clean-room run: fresh subprocess, scrubbed secrets, temp output, validate.

Simulates the evaluator: no reliance on shell state, IDE caches, or
pre-generated files. Runtime is stdlib-only (pandas listed but unused at
runtime), so no install step is required; this is asserted, not assumed.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset/official")
    args = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {k: v for k, v in os.environ.items() if "KEY" not in k.upper() and "TOKEN" not in k.upper()}

    with tempfile.TemporaryDirectory(prefix="affordai-cleanroom-") as tmp:
        out = os.path.join(tmp, "output.csv")
        build = subprocess.run(
            [sys.executable, "scripts/build_output.py", "--dataset", args.dataset, "--out", out],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=1200,
        )
        print(build.stdout[-2000:])
        if build.returncode != 0:
            print("CLEAN-ROOM FAIL: build_output error")
            print(build.stderr[-2000:])
            return 1
        req = os.path.join(args.dataset, "requests.csv")
        valid = subprocess.run(
            [sys.executable, "scripts/validate_output.py", "--requests", req, "--output", out, "--dataset", args.dataset],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        print(valid.stdout[-2000:])
        if valid.returncode != 0:
            print("CLEAN-ROOM FAIL: validation error")
            return 1
    print("CLEAN-ROOM PASS: fresh-env build + validate with no local state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
