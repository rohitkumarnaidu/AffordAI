"""Deterministic plan ranking (official 6-rule order, exact).

1. complete by deadline  2. no spending changes  3. min total paid
4. earlier start  5. fewer payments  6. lowest payment_option_id.
No model output may alter ranking: inputs are validated Candidates only.
"""
from __future__ import annotations


def rank_key(candidate, deadline):
    """Six-level official ordering (first match wins).

    Non-installment candidates carry ``option_id=None``, which sorts as
    ``"~~~"`` (after any real option id) — deterministic and documented.
    A residual full tie (identical 6-tuple) falls through to the input
    list order; inputs are deterministically built (``payment_plans``
    generation order + sorted targets + ``combinations`` order), so
    ``min`` stays reproducible run to run.
    """
    return (
        1 if candidate.last_date > deadline else 0,
        1 if candidate.changes else 0,
        candidate.total_paid,
        candidate.first_date,
        len(candidate.payments),
        candidate.option_id if candidate.option_id is not None else "~~~",
    )


def select(candidates: list, deadline):
    """Return the winning candidate (first match wins)."""
    return min(candidates, key=lambda c: rank_key(c, deadline))
