"""Typed loader: dataset/official/financial_events.csv (25342 rows).

Nullability (measured): amount blank 16 (-> image), settlement_date blank 10
(all non-cash valuations -> fall back to event_date, recorded), rest required.
"""
from __future__ import annotations

from affordai.ingestion import (
    DatasetError,
    check_duplicates,
    parse_amount_safe,
    parse_date,
    read_table,
    require_date,
)

REQUIRED = [
    "event_id",
    "user_id",
    "event_type",
    "description",
    "category",
    "direction",
    "amount",
    "currency",
    "event_date",
    "settlement_date",
    "status",
    "linked_event_id",
    "flexibility",
    "minimum_allowed_amount",
]

STATUSES = {
    "settled",
    "pending",
    "scheduled",
    "cancelled",
    "failed",
    "unrealized",
}


def load(path: str) -> list[dict]:
    raw = read_table(path, REQUIRED)
    check_duplicates(raw, "event_id", "events")
    rows: list[dict] = []
    for r in raw:
        eid = r["event_id"].strip()
        event_date = require_date(r["event_date"], f"events {eid}.event_date")
        settlement = parse_date(r["settlement_date"], f"events {eid}.settlement_date")
        if settlement is None:
            # Observed only on non-cash rows; fall back deterministically.
            settlement = event_date
        status = r["status"].strip()
        if status not in STATUSES:
            raise DatasetError(f"events {eid}: unknown status {status!r}")
        rows.append(
            {
                "event_id": eid,
                "user_id": r["user_id"].strip(),
                "event_type": r["event_type"].strip(),
                "description": r["description"],
                "category": r["category"].strip(),
                "direction": r["direction"].strip(),
                # None = blank -> must be resolved via images.csv, NEVER zero.
                "amount": parse_amount_safe(r["amount"], f"events {eid}.amount"),
                "currency": r["currency"].strip(),
                "event_date": event_date,
                "settlement_date": settlement,
                "settlement_fallback": not str(r["settlement_date"] or "").strip(),
                "status": status,
                "linked_event_id": r["linked_event_id"].strip() or None,
                "flexibility": r["flexibility"].strip(),
                "minimum_allowed_amount": parse_amount_safe(
                    r["minimum_allowed_amount"], f"events {eid}.minimum_allowed_amount"
                ),
            }
        )
    return rows
