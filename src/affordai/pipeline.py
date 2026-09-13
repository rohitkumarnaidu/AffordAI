"""AffordAI pipeline orchestrator (Milestone 2 implements stages)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RequestContext:
    original_index: int
    request_id: str
    user_id: str
    request: dict
    profile: dict
    events: list
    messages: list
    images: list
    payment_options: list
    evidence: list
