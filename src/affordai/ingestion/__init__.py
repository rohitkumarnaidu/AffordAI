"""Shared typed-ingestion helpers (CSV reading, parsing, identity checks)."""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal

from affordai.finance.money import parse_amount


class DatasetError(Exception):
    """Fatal dataset problem: missing file/column, malformed required value."""


def read_table(path: str, required: list[str]) -> list[dict]:
    """Read a CSV, enforcing required headers. Returns raw-string rows."""
    try:
        fh = open(path, newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise DatasetError(f"cannot open {path}: {exc}")
    with fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise DatasetError(f"{path}: missing header row")
        missing = [c for c in required if c not in reader.fieldnames]
        if missing:
            raise DatasetError(f"{path}: missing columns {missing}")
        return [dict(r) for r in reader]


def parse_date(raw: object, what: str) -> date | None:
    if raw is None or str(raw).strip() == "":
        return None
    text = str(raw).strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise DatasetError(f"{what}: bad date {raw!r} (expected YYYY-MM-DD)")


def require_date(raw: object, what: str) -> date:
    value = parse_date(raw, what)
    if value is None:
        raise DatasetError(f"{what}: missing required date")
    return value


def parse_datetime(raw: object, what: str) -> datetime | None:
    """Parse ISO timestamps (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)."""
    if raw is None or str(raw).strip() == "":
        return None
    text = str(raw).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise DatasetError(f"{what}: bad timestamp {raw!r}")


def require_decimal(raw: object, what: str) -> Decimal:
    try:
        value = parse_amount(raw)
    except ValueError:
        raise DatasetError(f"{what}: malformed amount {raw!r}")
    if value is None:
        raise DatasetError(f"{what}: missing required amount")
    return value


def parse_amount_safe(raw: object, what: str) -> Decimal | None:
    """parse_amount with malformed input mapped to DatasetError (blank -> None)."""
    try:
        return parse_amount(raw)
    except ValueError:
        raise DatasetError(f"{what}: malformed amount {raw!r}")


def parse_bool(raw: object, what: str) -> bool:
    text = str(raw).strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no"):
        return False
    raise DatasetError(f"{what}: bad boolean {raw!r}")


def check_duplicates(rows: list[dict], key: str, what: str) -> None:
    seen: set[str] = set()
    dupes: list[str] = []
    for row in rows:
        kid = row[key]
        if kid in seen:
            dupes.append(str(kid))
        seen.add(kid)
    if dupes:
        raise DatasetError(f"{what}: duplicate {key}: {dupes[:5]}")
