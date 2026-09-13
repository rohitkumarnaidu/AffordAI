"""Typed loader: dataset/official/requests.csv (250 eval rows)."""
from __future__ import annotations

from affordai.ingestion import (
    DatasetError,
    check_duplicates,
    parse_bool,
    read_table,
    require_date,
    require_decimal,
)

REQUIRED = [
    "request_id",
    "user_id",
    "request_date",
    "request_type",
    "requested_amount",
    "desired_completion_date",
    "allows_partial_payment",
    "request_text",
]


def load(path: str) -> list[dict]:
    raw = read_table(path, REQUIRED)
    check_duplicates(raw, "request_id", "requests")
    rows: list[dict] = []
    for i, r in enumerate(raw):
        if not r["request_id"].strip() or not r["user_id"].strip():
            raise DatasetError(f"requests row {i}: blank request_id/user_id")
        rows.append(
            {
                "original_index": i,
                "request_id": r["request_id"].strip(),
                "user_id": r["user_id"].strip(),
                "request_date": require_date(
                    r["request_date"], f"requests {r['request_id']}.request_date"
                ),
                "request_type": r["request_type"].strip(),
                "requested_amount": require_decimal(
                    r["requested_amount"], f"requests {r['request_id']}.requested_amount"
                ),
                "desired_completion_date": require_date(
                    r["desired_completion_date"],
                    f"requests {r['request_id']}.desired_completion_date",
                ),
                "allows_partial_payment": parse_bool(
                    r["allows_partial_payment"],
                    f"requests {r['request_id']}.allows_partial_payment",
                ),
                "request_text": r["request_text"],
            }
        )
    return rows
