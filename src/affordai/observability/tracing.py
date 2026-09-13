"""Structured per-request tracing (diagnostics only, never secrets).

Sec 31.3: every detail string is redacted before storage so API keys /
tokens / passwords can never enter traces.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from affordai.security.redact import redact


@dataclass
class TraceEvent:
    stage: str
    request_id: str
    detail: str = ""


@dataclass
class Trace:
    events: list[TraceEvent] = field(default_factory=list)

    def record(self, stage: str, request_id: str, detail: str = "") -> None:
        self.events.append(TraceEvent(stage, request_id, redact(detail)))

    def for_request(self, request_id: str) -> list[TraceEvent]:
        return [e for e in self.events if e.request_id == request_id]
