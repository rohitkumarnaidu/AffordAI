"""Structured per-request tracing (diagnostics only, never secrets)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TraceEvent:
    stage: str
    request_id: str
    detail: str = ""


@dataclass
class Trace:
    events: list[TraceEvent] = field(default_factory=list)

    def record(self, stage: str, request_id: str, detail: str = "") -> None:
        self.events.append(TraceEvent(stage, request_id, detail))

    def for_request(self, request_id: str) -> list[TraceEvent]:
        return [e for e in self.events if e.request_id == request_id]
