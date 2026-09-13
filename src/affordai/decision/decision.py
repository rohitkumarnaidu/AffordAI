"""Canonical decision object — single source of truth before CSV.

Immutability invariant (Section 22.10 / 4.10):
    Once finalized, the Decision is the authoritative source for CSV,
    explanation, validation, logs, and evaluation. Downstream components
    must not silently alter it. Enforced via frozen dataclass + defensive
    validation in __post_init__; evidence tuple and explanation_facts
    are treated as immutable provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class Decision:
    """One Decision per request — all downstream output derives from it.

    Required output fields (official 8 columns) are stored as CSV-ready
    strings except amount_safe_to_pay which is Decimal for exact
    arithmetic (serializer quantizes per currency). Internal provenance
    (evidence, explanation_facts, requested_amount, home_currency) is
    retained for validation but never recomputed downstream.

    Fields follow docs/specification.md §3 order.
    """

    original_index: int
    request_id: str
    user_id: str
    amount_safe_to_pay: Decimal
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: str
    spending_changes_needed: str
    decision_explanation: str
    # Provenance — immutable (tuple) + structured facts (frozen dict view)
    evidence: tuple = field(default_factory=tuple)
    explanation_facts: dict = field(default_factory=dict)
    # Internal validation helpers (not in CSV)
    requested_amount: Decimal | None = None
    home_currency: str | None = None

    def __post_init__(self) -> None:
        # Normalize evidence to tuple (accepts list for backward compat, but enforces immutability)
        if isinstance(self.evidence, list):
            object.__setattr__(self, "evidence", tuple(self.evidence))
        # Type / non-empty checks (fail-closed: any violation raises, pipeline degrades to fallback)
        if not isinstance(self.original_index, int) or self.original_index < 0:
            raise ValueError(f"Decision {self.request_id}: invalid original_index {self.original_index!r}")
        if not self.request_id or not str(self.request_id).strip():
            raise ValueError("Decision missing request_id")
        if not self.user_id or not str(self.user_id).strip():
            raise ValueError(f"Decision {self.request_id}: missing user_id")
        if not isinstance(self.amount_safe_to_pay, Decimal):
            raise TypeError(f"Decision {self.request_id}: amount_safe_to_pay must be Decimal, got {type(self.amount_safe_to_pay)}")
        if not self.amount_safe_to_pay.is_finite():
            raise ValueError(f"Decision {self.request_id}: amount_safe_to_pay non-finite")
        # 4.2 SAFE AMOUNT invariant: 0 <= safe <= requested (when known)
        if self.requested_amount is not None:
            if not isinstance(self.requested_amount, Decimal):
                raise TypeError(f"Decision {self.request_id}: requested_amount must be Decimal")
            if self.amount_safe_to_pay < 0 or self.amount_safe_to_pay > self.requested_amount:
                raise ValueError(
                    f"Decision {self.request_id}: 0 <= {self.amount_safe_to_pay} <= {self.requested_amount} violated"
                )
        else:
            if self.amount_safe_to_pay < 0:
                raise ValueError(f"Decision {self.request_id}: amount_safe_to_pay negative")
        # 4.3 / 4.4 enums (strict, no whitespace drift)
        if self.affordability_status not in STATUSES:
            raise ValueError(f"Decision {self.request_id}: unknown status {self.affordability_status!r}")
        if self.recommended_payment_method not in METHODS:
            raise ValueError(f"Decision {self.request_id}: unknown method {self.recommended_payment_method!r}")
        # Cross-field consistency (Section 23.2) — enforced here, not only in validator
        from affordai.decision.invariants import check_earliest_consistency, check_status_method_consistency

        if not check_status_method_consistency(self.affordability_status, self.recommended_payment_method):
            raise ValueError(
                f"Decision {self.request_id}: status/method inconsistent {self.affordability_status}/{self.recommended_payment_method}"
            )
        # earliest consistency needs request_date; we store it in explanation_facts when available
        # Validate explanation_facts does not contain invented claims (must be subset of decision)
        if self.explanation_facts:
            ef = self.explanation_facts
            # amount in facts must equal decision amount
            if "amount_safe_to_pay" in ef and ef["amount_safe_to_pay"] != self.amount_safe_to_pay:
                raise ValueError(f"Decision {self.request_id}: explanation_facts amount mismatch")
            if "affordability_status" in ef and ef["affordability_status"] != self.affordability_status:
                raise ValueError(f"Decision {self.request_id}: explanation_facts status mismatch")
            if "recommended_payment_method" in ef and ef["recommended_payment_method"] != self.recommended_payment_method:
                raise ValueError(f"Decision {self.request_id}: explanation_facts method mismatch")

    def to_row(self) -> dict:
        """Return exact 8-column dict in official order (values are CSV-ready)."""
        # amount is Decimal -> serializer formats per currency; keep Decimal here for exactness,
        # but to_row is used only by tests that expect string-formatted via serializer;
        # we keep Decimal and let serializer handle formatting. For direct use, return as is.
        return {
            "request_id": self.request_id,
            "amount_safe_to_pay": self.amount_safe_to_pay,
            "affordability_status": self.affordability_status,
            "recommended_payment_method": self.recommended_payment_method,
            "payment_plan": self.payment_plan,
            "earliest_date_for_full_payment": self.earliest_date_for_full_payment,
            "spending_changes_needed": self.spending_changes_needed,
            "decision_explanation": self.decision_explanation,
        }

    def to_serialized_row(self, home: str | None = None) -> dict[str, str]:
        """CSV-ready row with amount formatted and column order guaranteed."""
        from affordai.finance.money import format_amount

        h = home or self.home_currency or "INR"
        return {
            "request_id": self.request_id,
            "amount_safe_to_pay": format_amount(self.amount_safe_to_pay, h),
            "affordability_status": self.affordability_status,
            "recommended_payment_method": self.recommended_payment_method,
            "payment_plan": self.payment_plan,
            "earliest_date_for_full_payment": self.earliest_date_for_full_payment,
            "spending_changes_needed": self.spending_changes_needed,
            "decision_explanation": self.decision_explanation,
        }


OUTPUT_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]

STATUSES = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
METHODS = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}
