"""Token/cost accounting for the FINAL full-dataset run (usage_report.md).

Sec 32.3: every model call captures timestamp/request_id/provider/model/
purpose/input/output tokens/success/retry/fallback. Pricing is kept separate
from business logic (PRICING table below). Token source is explicit:
`estimated` (local chars/4 heuristic, LOCAL MEASUREMENT) vs `provider`
(actual provider-reported usage). Cost is transparent or UNKNOWN if pricing
cannot be verified. No prompt/secret text is ever stored in records.

Single source of truth — no duplicate token accounting elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from affordai.security.redact import redact

# Pricing is configuration, not business logic. Keep separate from pipeline.
# Values are illustrative per-1K-token rates; UNKNOWN when unverified.
# E0 deterministic run has 0 cost regardless.
PRICING: dict[str, dict[str, float]] = {
    # provider/model -> per-1K rates
    # Populate from your actual contract before a metered run, else COST=UNKNOWN.
    # e.g. "openai/gpt-4o": {"input_per_1k": 0.005, "output_per_1k": 0.015},
}


def _cost_for(model_key: str, input_tokens: int, output_tokens: int) -> float | None:
    entry = PRICING.get(model_key)
    if entry is None:
        return None
    try:
        return (input_tokens / 1000) * float(entry["input_per_1k"]) + (output_tokens / 1000) * float(entry["output_per_1k"])
    except Exception:
        return None


@dataclass
class UsageReport:
    provider: str = ""
    model: str = ""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    note: str = ""
    per_model: dict = field(default_factory=dict)
    records: list = field(default_factory=list)  # list[ModelCallRecord]

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def merge(self, other: "UsageReport") -> "UsageReport":
        merged_per: dict = {}
        for src in (self.per_model, other.per_model):
            for key, vals in (src or {}).items():
                bucket = merged_per.setdefault(key, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
                bucket["calls"] += int(vals.get("calls", 0))
                bucket["input_tokens"] += int(vals.get("input_tokens", 0))
                bucket["output_tokens"] += int(vals.get("output_tokens", 0))
        return UsageReport(
            provider=self.provider or other.provider,
            model=self.model or other.model,
            calls=self.calls + other.calls,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            note="; ".join(n for n in (self.note, other.note) if n),
            per_model=merged_per,
            records=list(self.records) + list(other.records),
        )

    def avg_tokens_per_request(self, n_requests: int) -> float:
        return self.total_tokens / n_requests if n_requests else 0.0

    def avg_cost_per_request(self, n_requests: int) -> float | None:
        total = self.estimated_total_cost()
        if total is None or not n_requests:
            return None
        return total / n_requests

    def estimated_total_cost(self) -> float | None:
        if not self.calls:
            return 0.0
        # Aggregate per-model costs; if any model lacks pricing -> UNKNOWN.
        total: float | None = 0.0
        for key, vals in (self.per_model or {}).items():
            model_key = "/".join(k for k in key if k) if isinstance(key, tuple) else str(key)
            c = _cost_for(model_key, int(vals.get("input_tokens", 0)), int(vals.get("output_tokens", 0)))
            if c is None:
                return None
            total += c
        # Fallback single-model path
        if not self.per_model and self.model:
            probe = _cost_for(f"{self.provider}/{self.model}" if self.provider else self.model,
                              self.input_tokens, self.output_tokens)
            if probe is None:
                # No verified pricing -> cost is UNKNOWN, not fabricated 0.
                return None
            return probe
        return total

    def to_markdown(self, n_requests: int, runtime_s: float) -> str:
        avg = self.avg_tokens_per_request(n_requests)
        total_cost = self.estimated_total_cost()
        per_req_cost = self.avg_cost_per_request(n_requests)
        if total_cost is None:
            total_cost_s = "UNKNOWN (no verified pricing for model)"
            per_req_s = "UNKNOWN"
        else:
            total_cost_s = f"{total_cost:.4f}"
            per_req_s = f"{per_req_cost:.6f}" if per_req_cost is not None else "UNKNOWN"
        token_source = "estimated (local chars/4)" if not self.records else ", ".join(
            sorted({getattr(r, "token_source", "estimated") for r in self.records})
        )
        # Secret-safe: redact note and provider/model strings before rendering
        safe_note = redact(self.note) if self.note else ""
        safe_provider = redact(self.provider) if self.provider else ""
        safe_model = redact(self.model) if self.model else ""
        lines = [
            "# Usage Report — FINAL full-dataset run",
            "",
            f"- Model provider: {safe_provider or '(deterministic E0, none)'}",
            f"- Model name(s): {safe_model or '(none)'}",
            f"- Model calls: {self.calls}",
            f"- Input tokens: {self.input_tokens}",
            f"- Output tokens: {self.output_tokens}",
            f"- Total tokens: {self.total_tokens}",
            f"- Average tokens/request: {avg:.1f}",
            f"- Estimated total cost: {total_cost_s}",
            f"- Estimated cost/request: {per_req_s}",
            f"- Requests processed: {n_requests}",
            f"- Wall runtime (s): {runtime_s:.1f}",
            f"- Token source: {token_source}",
            f"- Note: {safe_note}",
            "",
        ]
        if self.per_model:
            lines.append("Per-model breakdown:")
            lines.append("")
            lines.append("| Provider | Model | Calls | Input Tokens | Output Tokens | Total Tokens | Estimated Cost |")
            lines.append("|---|---|---|---|---|---|---|")
            for (prov, mod), vals in sorted(self.per_model.items()):
                tot = int(vals.get("input_tokens", 0)) + int(vals.get("output_tokens", 0))
                mk = f"{prov}/{mod}" if prov else mod
                cost = _cost_for(mk, int(vals.get("input_tokens", 0)), int(vals.get("output_tokens", 0)))
                cost_s = f"{cost:.4f}" if cost is not None else "UNKNOWN"
                lines.append(
                    f"| {prov or '(none)'} | {mod or '(none)'} | {vals.get('calls', 0)} | "
                    f"{vals.get('input_tokens', 0)} | {vals.get('output_tokens', 0)} | {tot} | {cost_s} |"
                )
            lines.append("")
        else:
            lines.append("Per-model breakdown (if multiple models): n/a -- deterministic run.")
            lines.append("")
        # Secret-safety attestation
        lines.append("Security: this report contains no prompts, API keys, or secrets -- counts only.")
        lines.append("")
        return "\n".join(lines)
