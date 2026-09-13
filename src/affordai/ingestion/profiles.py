"""Typed loader: dataset/official/financial_profiles.csv (275 users)."""
from __future__ import annotations

from affordai.ingestion import (
    DatasetError,
    check_duplicates,
    parse_amount_safe,
    read_table,
)

REQUIRED = [
    "user_id",
    "home_currency",
    "current_available_balance",
    "minimum_balance_to_keep",
    "financial_priorities",
    "expense_categories_to_protect",
    "expense_categories_user_is_willing_to_reduce",
    "expense_categories_user_is_willing_to_stop",
    "payment_methods_user_will_consider",
    "max_installment_months",
]


def _split_list(raw: str) -> list[str]:
    import re

    return [p.strip() for p in re.split(r"[;,|]", str(raw or "")) if p.strip()]


def load(path: str) -> dict:
    from affordai.ingestion import require_decimal

    raw = read_table(path, REQUIRED)
    check_duplicates(raw, "user_id", "profiles")
    profiles: dict = {}
    for r in raw:
        uid = r["user_id"].strip()
        if not uid:
            raise DatasetError("profiles: blank user_id")
        max_inst = (r["max_installment_months"] or "").strip()
        profiles[uid] = {
            "user_id": uid,
            "home_currency": r["home_currency"].strip(),
            "current_available_balance": require_decimal(
                r["current_available_balance"], f"profiles {uid}.balance"
            ),
            "minimum_balance_to_keep": require_decimal(
                r["minimum_balance_to_keep"], f"profiles {uid}.minimum"
            ),
            "financial_priorities": _split_list(r["financial_priorities"]),
            "expense_categories_to_protect": _split_list(
                r["expense_categories_to_protect"]
            ),
            "willing_to_reduce": _split_list(
                r["expense_categories_user_is_willing_to_reduce"]
            ),
            "willing_to_stop": _split_list(
                r["expense_categories_user_is_willing_to_stop"]
            ),
            # Blank max_installment_months = user refuses installments.
            "max_installment_months": int(max_inst) if max_inst else None,
            "methods_will_consider": _split_list(
                r["payment_methods_user_will_consider"]
            ),
        }
    return profiles
