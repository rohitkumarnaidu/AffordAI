"""Deterministic CSV serialization (exact columns/order/row identity).

Section 25 invariant:
    Serializer is deliberately boring — it converts the canonical Decision
    into the exact official 8-column schema. It must NOT make business
    decisions, recompute amounts/dates/totals, or alter the Decision.

    EXACT_COLUMNS is the single authoritative schema; output.columns
    == EXACT_COLUMNS is enforced before write.
"""
from __future__ import annotations

import csv
import re

from affordai.decision.decision import OUTPUT_COLUMNS
from affordai.finance.money import format_amount

# Single authoritative schema (Section 25.1)
EXACT_COLUMNS = OUTPUT_COLUMNS

# Deterministic date formatter: YYYY-MM-DD or "" (Section 25.6)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def format_date(d) -> str:
    """Format a date as YYYY-MM-DD or "" deterministically (no LLM)."""
    if d is None or d == "":
        return ""
    if hasattr(d, "isoformat"):
        s = d.isoformat()
    else:
        s = str(d).strip()
    if s == "":
        return ""
    # Validate shape YYYY-MM-DD (single-digit month/day is zero-padded by isoformat)
    if not _DATE_RE.match(s):
        # Try to parse and re-format (bounds: month boundary, year boundary, leap-day)
        from datetime import datetime

        try:
            dt = datetime.strptime(s, "%Y-%m-%d").date()
            return dt.isoformat()
        except ValueError:
            raise ValueError(f"invalid date format {s!r}, expected YYYY-MM-DD")
    return s


def format_plan(payments: list[tuple] | None, currency: str) -> str:
    """Format payments as YYYY-MM-DD:amount|... or 'none' (Section 25.7).

    Derives directly from canonical plan — does not recompute amounts/dates/totals.
    Chronology is enforced by caller; this formatter preserves order.
    """
    if not payments:
        return "none"
    # If already a string (canonical Decision stores formatted plan), return as-is
    if isinstance(payments, str):
        return payments
    # payments is list[tuple[date, Decimal]]
    parts = []
    for d, a in payments:
        ds = format_date(d)
        parts.append(f"{ds}:{format_amount(a, currency)}")
    return "|".join(parts)


def format_changes(changes: dict[str, object] | str | None, currency: str) -> str:
    """Serialize already-validated spending changes (Section 25.8).

    Input is validated set: <=3 flexible recurring only, no duplicate mutation.
    This formatter only joins them with required syntax, preserving sorted order.
    """
    if not changes or changes == "none":
        return "none"
    if isinstance(changes, str):
        return changes
    parts = []
    for event_id in sorted(changes):
        new_amount = changes[event_id]
        if new_amount is None:
            parts.append(f"stop:{event_id}")
        else:
            parts.append(f"reduce_to:{event_id}:{format_amount(new_amount, currency)}")
    return "|".join(parts)


def decisions_to_rows(decisions: list, home_by_request: dict[str, str]) -> list[dict]:
    """Convert canonical Decisions to CSV-ready rows (Section 25).

    Enforces:
        - Decisions must be sorted by original_index (hard failure if not)
        - One row per request, no duplicates
        - Exact 8 columns in exact order (constructed explicitly)
        - Amounts formatted via format_amount (no float), dates via format_date
        - CSV escaping handled by csv.DictWriter (not manual concatenation)
        - Row order == input order == original_index order
    """
    if not decisions:
        return []
    # 25.4 ORIGINAL REQUEST ORDER: verify sorted by original_index
    indices = [d.original_index for d in decisions]
    if indices != sorted(indices):
        raise ValueError(f"decisions not sorted by original_index: {indices[:5]}... (hard failure, blocks submission)")
    # 25.3 ONE ROW PER REQUEST + 25.2 identity: check duplicates
    seen = set()
    for d in decisions:
        if d.request_id in seen:
            raise ValueError(f"duplicate request_id {d.request_id} in decisions (hard failure)")
        seen.add(d.request_id)
    rows: list[dict] = []
    for d in decisions:
        home = home_by_request.get(d.request_id)
        if home is None:
            # Fallback to Decision's own home if mapping missing (defense in depth)
            home = getattr(d, "home_currency", None) or "INR"
        # Serializer must NOT recompute financial decision — only format validated fields
        plan = (
            d.payment_plan
            if isinstance(d.payment_plan, str)
            else format_plan(d.payment_plan, home)
        )
        changes = (
            d.spending_changes_needed
            if isinstance(d.spending_changes_needed, str)
            else format_changes(d.spending_changes_needed, home)
        )
        # Date formatting (deterministic, validates shape)
        earliest = format_date(d.earliest_date_for_full_payment)
        # Amount formatting (exact, no NaN/Infinity)
        amount_str = format_amount(d.amount_safe_to_pay, home)
        # Explicit construction in official order (never depends on dict insertion)
        row = {
            "request_id": d.request_id,
            "amount_safe_to_pay": amount_str,
            "affordability_status": d.affordability_status,
            "recommended_payment_method": d.recommended_payment_method,
            "payment_plan": plan,
            "earliest_date_for_full_payment": earliest,
            "spending_changes_needed": changes,
            "decision_explanation": d.decision_explanation,
        }
        # Enforce exact columns (no extra/missing)
        if list(row.keys()) != EXACT_COLUMNS:
            raise ValueError(f"row columns {list(row.keys())} != {EXACT_COLUMNS}")
        rows.append(row)
    return rows


def write_output_csv(decisions: list, home_by_request: dict[str, str], out_path: str) -> None:
    """Write decisions to CSV with standards-compliant escaping (Section 25.5).

    Uses csv.DictWriter with quoting=QUOTE_MINIMAL to correctly handle
    comma, quote, newline, colon, semicolon, unicode, empty string.
    Round-trip: serialize -> parse -> values identical is guaranteed.
    """
    rows = decisions_to_rows(decisions, home_by_request)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=EXACT_COLUMNS,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
            doublequote=True,
            escapechar=None,
        )
        writer.writeheader()
        writer.writerows(rows)
