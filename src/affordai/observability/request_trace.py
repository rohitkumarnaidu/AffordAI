"""Structured per-request trace — Section 33 (Winning Checklist).

One ``RequestTrace`` answers: "Why did AffordAI produce this exact output
row for this exact request?" Chain recorded::

    request -> evidence -> extracted facts -> financial state -> forecast
    -> candidate plans -> rejected plans + reasons -> selected plan
    -> final decision -> output row

Design rules (no overengineering):
- Diagnostics only. The trace RECORDS what the deterministic engine did;
  it is never a source of financial truth and never feeds back into
  decisions, ranking, or simulation.
- Secret-safe: every free-text detail passes through
  ``security.redact.redact`` before storage (reuses Sec 31.3 mechanism).
  Financial amounts/dates/ids are operational data (not secrets) and are
  kept so the trace stays debuggable.
- Deterministic ``trace_id``: ``sha256(run_id|request_id|original_index)``
  truncated to 16 hex chars. Same request + same run id -> same trace id
  (tested). Wall-clock start/end times are informational only.
- Request isolation: one object per request; no cross-request references.
  ``RequestTraceStore`` below is a plain dict wrapper with a JSON exporter
  used by ``scripts/trace_request.py`` (interview debugging).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field

from affordai.security.redact import redact


def make_trace_id(run_id: str, request_id: str, original_index: int) -> str:
    """Deterministic trace id (no randomness, no clock)."""
    blob = f"{run_id}|{request_id}|{original_index}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


@dataclass
class RequestTrace:
    """Full 10-section execution trace for ONE request."""

    request_id: str
    original_row_index: int
    trace_id: str = ""
    run_id: str = "E0"
    start_time: float = 0.0
    end_time: float = 0.0
    status: str = "pending"  # ok | fallback | error
    # B. evidence ids (never full sensitive objects)
    evidence: dict = field(default_factory=dict)
    # C. extracted facts (provenance dicts from Evidence.provenance())
    facts: list = field(default_factory=list)
    rejected_facts: list = field(default_factory=list)
    llm_fallback: str = ""
    # D. deterministic financial state summary
    financial_state: dict = field(default_factory=dict)
    # E. forecast debug summary
    forecast: dict = field(default_factory=dict)
    # F/G/H. candidates, rejections, selection
    candidates: list = field(default_factory=list)
    rejected_plans: list = field(default_factory=list)
    selected_plan: dict = field(default_factory=dict)
    # I. final validated decision (8 output fields + status/method)
    final_decision: dict = field(default_factory=dict)
    # J. output-row mapping
    output_row: dict = field(default_factory=dict)
    # failure/fallback log (Sec 34: every fallback appears here)
    failures: list = field(default_factory=list)

    def finish(self, status: str) -> None:
        self.status = status
        try:
            self.end_time = time.time()
        except Exception:
            self.end_time = self.start_time

    def log_failure(self, kind: str, detail: str) -> None:
        try:
            self.failures.append({"kind": kind, "detail": redact(detail)[:300]})
        except Exception:
            pass

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration_s"] = round((self.end_time - self.start_time), 4) if self.end_time >= self.start_time else 0.0
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=1, default=str)


class RequestTraceStore(dict):
    """request_id -> RequestTrace with secret-safe JSON export."""

    def to_json_file(self, path: str) -> None:
        blob = {rid: tr.to_dict() for rid, tr in self.items()}
        # Defense-in-depth: redact the serialized blob string once more.
        text = redact(json.dumps(blob, indent=1, default=str))
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def for_request(self, request_id: str) -> RequestTrace | None:
        return self.get(request_id)
