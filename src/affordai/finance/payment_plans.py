"""Candidate payment-plan generation (shapes only; safety decided by forecast)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from affordai.ingestion.payment_options import expand_schedule


@dataclass
class Candidate:
    kind: str  # full | partial | installments | wait
    payments: list[tuple[date, Decimal]]
    option_id: str | None = None
    total_paid: Decimal = Decimal("0")
    changes: dict[str, Decimal | None] = field(default_factory=dict)

    @property
    def first_date(self) -> date:
        return min(d for d, _ in self.payments)

    @property
    def last_date(self) -> date:
        return max(d for d, _ in self.payments)


def generate(
    state,
    options: list[dict],
    safe: Decimal,
    earliest: date | None,
    allows_partial: bool,
) -> tuple[list[Candidate], list[str]]:
    """Build unvalidated candidate shapes. Returns (candidates, notes)."""
    req_date = state.request_date
    requested = state.requested
    out: list[Candidate] = []
    notes: list[str] = []
    out.append(
        Candidate(
            kind="full", payments=[(req_date, requested)], total_paid=requested
        )
    )
    if (
        allows_partial
        and Decimal("0") < safe < requested
        and earliest is not None
        and earliest <= state.deadline
    ):
        out.append(
            Candidate(
                kind="partial",
                payments=[(req_date, safe), (earliest, requested - safe)],
                total_paid=requested,
            )
        )
    for opt in options:
        if opt["payment_method"] != "installments":
            continue
        if opt["payment_frequency_days"] is None and opt["number_of_payments"] > 1:
            notes.append(f"option {opt['payment_option_id']}: malformed schedule, skipped")
            continue
        sched = expand_schedule(opt)
        out.append(
            Candidate(
                kind="installments",
                payments=sched,
                option_id=opt["payment_option_id"],
                total_paid=opt["total_payable_amount"],
            )
        )
    if earliest is not None and earliest > req_date:
        out.append(
            Candidate(
                kind="wait", payments=[(earliest, requested)], total_paid=requested
            )
        )
    return out, notes
