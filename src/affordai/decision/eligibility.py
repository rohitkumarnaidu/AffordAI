"""Method eligibility filtering (preferences + deadline, before ranking).

- full/partial/installments need membership in payment_methods_user_will_consider.
- installments additionally need max_installment_months set and option span
  within months*31 days (documented approximation of term length).
- partial additionally needs allows_partial_payment.
- wait needs user acceptance of full_payment (full becoming safe later is
  established by the candidate existing).
- any candidate completing after desired_completion_date is dropped
  (not_recommended fallback is assembled by the pipeline, not here).
- financial safety is NOT decided here: this filter checks preference +
  deadline + installment term only. ``pipeline`` re-simulates every
  surviving candidate via ``forecast.simulate`` afterwards, so an unsafe
  but preferred candidate passes this stage and is rejected there.
- partial's remaining conditions (``0 < safe < requested``,
  ``earliest <= deadline``, exact 2-leg shape) are enforced at
  generation time in ``finance/payment_plans.generate`` (and re-checked
  by ``output/validator``), not here.
"""
from __future__ import annotations

KIND_METHOD = {
    "full": "full_payment",
    "partial": "partial_payment",
    "installments": "installments",
    "wait": "full_payment",
}


def filter_candidates(
    candidates: list,
    profile: dict,
    allows_partial: bool,
    deadline,
) -> list:
    accepted = set(profile["methods_will_consider"])
    max_months = profile["max_installment_months"]
    out = []
    for c in candidates:
        if c.last_date > deadline:
            continue
        method = KIND_METHOD[c.kind]
        if method not in accepted:
            continue
        if c.kind == "partial" and not allows_partial:
            continue
        if c.kind == "installments":
            if max_months is None:
                continue
            span_days = (c.last_date - c.first_date).days
            if span_days > max_months * 31:
                continue
        out.append(c)
    return out
