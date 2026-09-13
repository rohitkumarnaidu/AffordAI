"""Token/cost accounting for the FINAL full-dataset run (usage_report.md)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UsageReport:
    provider: str = ""
    model: str = ""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    note: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def merge(self, other: "UsageReport") -> "UsageReport":
        return UsageReport(
            provider=self.provider or other.provider,
            model=self.model or other.model,
            calls=self.calls + other.calls,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            note="; ".join(n for n in (self.note, other.note) if n),
        )

    def to_markdown(self, n_requests: int, runtime_s: float) -> str:
        avg = self.total_tokens / n_requests if n_requests else 0
        return (
            "# Usage Report — FINAL full-dataset run\n\n"
            f"- Model provider: {self.provider or '(deterministic E0, none)'}\n"
            f"- Model name(s): {self.model or '(none)'}\n"
            f"- Model calls: {self.calls}\n"
            f"- Input tokens: {self.input_tokens}\n"
            f"- Output tokens: {self.output_tokens}\n"
            f"- Total tokens: {self.total_tokens}\n"
            f"- Average tokens/request: {avg:.1f}\n"
            f"- Estimated total cost: 0.00 (no model calls)\n"
            f"- Estimated cost/request: 0.00\n"
            f"- Requests processed: {n_requests}\n"
            f"- Wall runtime (s): {runtime_s:.1f}\n"
            f"- Note: {self.note}\n\n"
            "Per-model breakdown (if multiple models): n/a — deterministic run.\n"
        )
