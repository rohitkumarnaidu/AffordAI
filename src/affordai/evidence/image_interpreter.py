"""Image evidence resolver (deterministic side).

Resolves blank event amounts via the official relationship:
``financial_events.event_id -> images.csv:related_event_id ->
dataset/official/media/images/<image_id>.png``.

E0 performs mapping + file/ownership validation only. Amount extraction
itself is delegated to the bounded LLM/vision adapter when enabled;
without it the amount stays UNKNOWN (never zero) and plans must remain
safe without it.
"""
from __future__ import annotations

import os
from decimal import Decimal

from affordai.evidence.evidence_registry import Evidence


def resolve_images_for_event(
    event_id: str, image_rows: list[dict], media_dir: str
) -> list[dict]:
    """Return validated image descriptors linked to an event."""
    out = []
    for row in image_rows:
        if row["related_event_id"] != event_id:
            continue
        path = os.path.join(media_dir, f"{row['image_id']}.png")
        out.append(
            {
                "image_id": row["image_id"],
                "request_id": row["request_id"],
                "user_id": row["user_id"],
                "path": path,
                "file_exists": os.path.isfile(path),
            }
        )
    return out


def amount_unknown_evidence(
    event_id: str, image_id: str | None, request_id: str | None, user_id: str | None
) -> Evidence:
    """Provenance-marked UNKNOWN amount (blank is never zero)."""
    return Evidence(
        source_type="image",
        source_id=image_id or f"missing-image:{event_id}",
        request_id=request_id,
        user_id=user_id,
        event_id=event_id,
        image_id=image_id,
        kind="amount",
        raw_value="",
        normalized_value="unknown",
        confidence=Decimal("0"),
        method="deterministic",
    )
