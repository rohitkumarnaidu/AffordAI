"""Secret scan for the AffordAI submission (Sec 44/45: secrets gate).

Scans every git-tracked file + code.zip contents + output.csv for
credentials. Two tiers:

- FAIL (exit 1): high-confidence credential material or packaging violations
  (.env tracked, .env inside code.zip, private-key blocks, long provider
  key formats, key-like assignments outside tests/fixtures).
- WARN (exit 0): suspicious tokens inside tests/fixtures (dummy values used
  by redaction tests; listed explicitly so a human can confirm).

Thresholds are tuned so the repo's own dummy fixtures (short fakes such as
``sk-ant-1234567890abcdef``) do NOT trip FAIL -- verify by running:
``python scripts/scan_secrets.py`` must print SCAN CLEAN on a clean tree.
"""
from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# High-confidence key formats (lengths chosen above the repo's dummy fakes).
FAIL_PATTERNS = [
    ("private-key-block", re.compile(r"BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}")),
    ("slack-token", re.compile(r"xox[bpas]-[A-Za-z0-9\-]{8,}")),
    ("groq-key", re.compile(r"gsk_[A-Za-z0-9]{20,}")),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
]
ASSIGN_RE = re.compile(r"""(?i)\b(api[_-]?key|secret|passwd|password|bearer)\b\s*[:=]\s*['\"]([^'\"]{8,})['\"]""")

# Files/dirs where key-LOOKING dummy values are expected (redaction fixtures).
TESTISH = ("tests/", "test_", ".md", ".example")


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        return []
    return [l for l in out.stdout.splitlines() if l.strip()]


def main() -> int:
    fails: list[str] = []
    warns: list[str] = []

    tracked = _tracked_files()
    if not tracked:
        print("WARN: git ls-files empty/unavailable -- falling back to visible tree scan")
        tracked = [str(p.relative_to(ROOT)).replace("\\", "/") for p in ROOT.rglob("*") if p.is_file()]

    # 1. .env must never be tracked.
    if ".env" in tracked:
        fails.append("FAIL .env is git-tracked (must be ignored + untracked)")
    if "log.txt" in tracked:
        fails.append("FAIL log.txt is git-tracked (transcript stays out of git/package)")

    # 2. Content scan of tracked text files.
    for rel in tracked:
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="strict")
        except Exception:
            continue  # binary/unreadable: checked by name rules below
        if len(text) > 2_000_000:
            warns.append(f"WARN {rel}: >2MB, scanned fully anyway")
        for name, rx in FAIL_PATTERNS:
            m = rx.search(text)
            if m:
                if any(k in rel for k in TESTISH):
                    warns.append(f"WARN {rel}: {name} dummy fixture? {m.group(0)[:12]}...")
                else:
                    fails.append(f"FAIL {rel}: {name} match {m.group(0)[:12]}...")
        for m in ASSIGN_RE.finditer(text):
            if any(k in rel for k in ("tests/",)) or rel.endswith((".md", ".example")):
                warns.append(f"WARN {rel}: key-like assignment (test/doc fixture?) {m.group(1)}=...")
            else:
                fails.append(f"FAIL {rel}: key-like assignment {m.group(1)}=...")

    # 3. output.csv must contain no key-like tokens.
    out_csv = ROOT / "output.csv"
    if out_csv.is_file():
        blob = out_csv.read_text(encoding="utf-8", errors="replace")
        for name, rx in FAIL_PATTERNS:
            if rx.search(blob):
                fails.append(f"FAIL output.csv: {name} match")

    # 4. code.zip hygiene: no .env / keys / git / caches / absolute paths.
    zip_path = ROOT / "code.zip"
    if zip_path.is_file():
        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
        except Exception as exc:
            fails.append(f"FAIL code.zip unreadable: {exc}")
            names = []
        for n in names:
            base = n.split("/")[-1]
            low = n.lower()
            if base == ".env":
                fails.append("FAIL code.zip contains .env")
            if base in ("id_rsa", "id_ed25519") or low.endswith(".pem"):
                fails.append(f"FAIL code.zip contains key file {n}")
            if low.startswith(".git/") or "/.git/" in low:
                fails.append(f"FAIL code.zip contains .git entry {n}")
            if "__pycache__" in low or ".pytest_cache" in low or "node_modules" in low:
                fails.append(f"FAIL code.zip contains cache/env entry {n}")
            if n.startswith("/") or (len(n) > 2 and n[1] == ":"):
                fails.append(f"FAIL code.zip contains absolute path {n}")
            if base == "log.txt":
                fails.append("FAIL code.zip contains log.txt (transcript ships separately)")
    else:
        warns.append("WARN code.zip missing (nothing to inspect)")

    # 5. .env must never have been committed (history check).
    hist = subprocess.run(
        ["git", "log", "--oneline", "--", ".env"], cwd=ROOT,
        capture_output=True, text=True, check=False,
    )
    if hist.returncode == 0 and hist.stdout.strip():
        fails.append("FAIL .env appears in git history")

    for w in warns:
        print(w)
    for f in fails:
        print(f)
    if fails:
        print(f"SECRETS SCAN: {len(fails)} FAIL, {len(warns)} warnings -> BLOCKED")
        return 1
    print(f"SCAN CLEAN ({len(tracked)} tracked files checked, {len(warns)} warnings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
