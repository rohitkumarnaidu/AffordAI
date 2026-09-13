"""Final green-light gate (Checklist Sec 45): all applicable items must hold.

Usage:  python scripts/final_green_light_gate.py [--dataset dataset/official]

Runs the red-flag gate first (any FAIL short-circuits to NO-GO), then verifies
the green-light layer: required artifacts exist and are well-formed, docs are
present, the worktree matches a recorded commit, and packaging is clean.
Prints ``<name> ............... PASS|FAIL`` lines; exit 1 unless everything
is green. No "mostly green".
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import final_red_flag_gate as red

GREEN_FAILURES = 0


def greport(name: str, ok: bool, detail: str = "") -> None:
    global GREEN_FAILURES
    dots = "." * max(2, 30 - len(name))
    print(f"{name} {dots} {'PASS' if ok else 'FAIL'}" + (f" ({detail})" if detail else ""), flush=True)
    if not ok:
        GREEN_FAILURES += 1


def check_red_gate(dataset: str) -> bool:
    before = red.FAILURES
    red.check_identity(dataset)
    red.check_file_layers(dataset)
    red.check_replay_hash()
    red.check_artifact_finance(dataset)
    red.check_evidence_consistency()
    red.check_llm_boundary()
    red.check_attacks()
    red.check_secrets()
    red.check_usage_and_transcript()
    red.check_clean_room(dataset)
    red.check_regression()
    new_fails = red.FAILURES - before
    greport("red_gate_all_clear", new_fails == 0, f"{new_fails} red FAILs" if new_fails else "Sec 44 green")
    return new_fails == 0


def check_artifacts() -> bool:
    ok = True
    out = ROOT / "output.csv"
    rows = list(csv.DictReader(open(out, newline="", encoding="utf-8"))) if out.is_file() else []
    good = out.is_file() and len(rows) == 250
    greport("artifact_output_csv", good, f"{len(rows)} rows" if out.is_file() else "missing")
    ok &= good

    zp = ROOT / "code.zip"
    zip_ok = False
    detail = "missing"
    if zp.is_file():
        try:
            with zipfile.ZipFile(zp) as zf:
                names = zf.namelist()
                bad = zf.testzip()
            forbidden = [n for n in names if n.split("/")[-1] in (".env", "log.txt")
                         or "__pycache__" in n or ".pytest_cache" in n
                         or "/.git/" in n or n.startswith(".git/")]
            has_readme = any(n.split("/")[-1].lower() == "readme.md" for n in names)
            zip_ok = bad is None and not forbidden and has_readme
            detail = f"{len(names)} entries, readme={has_readme}, bad={bad}, forbidden={len(forbidden)}"
        except Exception as exc:
            detail = f"unreadable: {exc}"
    greport("artifact_code_zip", zip_ok, detail)
    ok &= zip_ok

    for rel in ("evaluation/usage_report.md", "log.txt",
                "evaluation/replay_report.md", "evaluation/full_dataset_report.md"):
        exists = (ROOT / rel).is_file()
        greport(f"artifact_{Path(rel).name}", exists, "" if exists else "missing")
        ok &= exists
    return ok


def check_docs() -> bool:
    ok = True
    required = ["README.md", "docs/specification.md", "docs/decision-matrix.md",
                "docs/data-model.md", "docs/architecture.md",
                "docs/evaluation-strategy.md", "docs/threat-model.md",
                "docs/interview-notes.md", "docs/build-checklist.md"]
    for rel in required:
        p = ROOT / rel
        good = p.is_file() and p.stat().st_size > 0
        greport(f"doc_{Path(rel).stem}", good, "" if good else "missing/empty")
        ok &= good
    return ok


def check_worktree() -> bool:
    r = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                       capture_output=True, text=True)
    dirty = [l for l in r.stdout.splitlines() if l.strip()]
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    greport("worktree_clean", not dirty, f"HEAD {head}" if not dirty else f"dirty: {dirty[:5]}")
    return not dirty


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset/official")
    args = ap.parse_args()
    print("FINAL GREEN-LIGHT GATE (Sec 45) -- all items must be true", flush=True)
    try:
        red_ok = check_red_gate(args.dataset)
        art_ok = check_artifacts()
        doc_ok = check_docs()
        tree_ok = check_worktree()
    except Exception as exc:
        greport("gate_crash", False, f"{type(exc).__name__}: {exc}"[:160])
        return 1
    green_ok = red_ok and art_ok and doc_ok and tree_ok and GREEN_FAILURES == 0
    print(f"GREEN-LIGHT GATE: {'GREEN' if green_ok else 'NO-GO (' + str(GREEN_FAILURES) + ' FAIL)'}", flush=True)
    return 0 if green_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
