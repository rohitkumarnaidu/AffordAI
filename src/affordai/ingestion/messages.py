"""Typed loader: messages.csv (215). Untrusted evidence (see evidence layer)."""
from __future__ import annotations

from affordai.ingestion import (
    DatasetError,
    check_duplicates,
    parse_datetime,
    read_table,
)

MSG_REQUIRED = [
    "message_id",
    "user_id",
    "request_id",
    "related_event_id",
    "sent_at",
    "source_type",
    "message_text",
]


def load_messages(path: str) -> list[dict]:
    raw = read_table(path, MSG_REQUIRED)
    check_duplicates(raw, "message_id", "messages")
    rows = []
    for r in raw:
        sent = parse_datetime(r["sent_at"], f"messages {r['message_id']}.sent_at")
        if sent is None:
            raise DatasetError(f"messages {r['message_id']}: missing sent_at")
        rows.append(
            {
                "message_id": r["message_id"].strip(),
                "user_id": r["user_id"].strip(),
                "request_id": r["request_id"].strip() or None,
                "related_event_id": r["related_event_id"].strip() or None,
                "sent_at": sent,
                "source_type": r["source_type"].strip(),
                "message_text": r["message_text"],
            }
        )
    return rows
