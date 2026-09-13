"""Typed loader: dataset/official/images.csv (16). Untrusted evidence links."""
from __future__ import annotations

from affordai.ingestion import DatasetError, check_duplicates, read_table

IMG_REQUIRED = ["image_id", "user_id", "request_id", "related_event_id"]


def load(path: str) -> list[dict]:
    raw = read_table(path, IMG_REQUIRED)
    check_duplicates(raw, "image_id", "images")
    rows = []
    for r in raw:
        if not r["image_id"].strip():
            raise DatasetError("images: blank image_id")
        rows.append(
            {
                "image_id": r["image_id"].strip(),
                "user_id": r["user_id"].strip(),
                "request_id": r["request_id"].strip() or None,
                "related_event_id": r["related_event_id"].strip() or None,
            }
        )
    return rows
