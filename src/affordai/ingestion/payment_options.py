"""Typed loader: dataset/official/request_payment_options.csv (790 rows)."""
from __future__ import annotations

from affordai.ingestion import (
    DatasetError,
    check_duplicates,
    parse_date,
    read_table,
    require_date,
    require_decimal,
)

REQUIRED = [
    "payment_option_id",
    "request_id",
    "payment_method",
    "payment_amount",
    "number_of_payments",
    "first_payment_date",
    "payment_frequency_days",
    "financing_fee",
    "total_payable_amount",
]


def _parse_int(raw: object, what: str) -> int | None:
    text = str(raw or "").strip()
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        raise DatasetError(f"{what}: bad integer {raw!r}")


def load(path: str) -> list[dict]:
    raw = read_table(path, REQUIRED)
    check_duplicates(raw, "payment_option_id", "payment_options")
    rows: list[dict] = []
    for r in raw:
        oid = r["payment_option_id"].strip()
        count = _parse_int(r["number_of_payments"], f"options {oid}.count")
        if count is None or count < 1:
            raise DatasetError(f"options {oid}: bad number_of_payments")
        rows.append(
            {
                "payment_option_id": oid,
                "request_id": r["request_id"].strip(),
                "payment_method": r["payment_method"].strip(),
                "payment_amount": require_decimal(
                    r["payment_amount"], f"options {oid}.payment_amount"
                ),
                "number_of_payments": count,
                # Blank frequency = single-payment option (observed 275x).
                "first_payment_date": require_date(
                    r["first_payment_date"], f"options {oid}.first_payment_date"
                ),
                "payment_frequency_days": _parse_int(
                    r["payment_frequency_days"], f"options {oid}.frequency"
                ),
                "financing_fee": require_decimal(
                    r["financing_fee"], f"options {oid}.financing_fee"
                ),
                "total_payable_amount": require_decimal(
                    r["total_payable_amount"], f"options {oid}.total_payable_amount"
                ),
            }
        )
    return rows


def expand_schedule(option: dict) -> list[tuple]:
    """Expand an option into dated (date, amount) payments (unvalidated)."""
    from datetime import timedelta

    first = option["first_payment_date"]
    freq = option["payment_frequency_days"] or 0
    out = []
    for k in range(option["number_of_payments"]):
        out.append((first + timedelta(days=freq * k), option["payment_amount"]))
    return out
