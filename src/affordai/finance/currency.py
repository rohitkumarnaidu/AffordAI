"""Dated FX conversion (assumption A1).

Rate selection: latest `exchange_rates.csv` row ON or BEFORE the cash
(settlement) date for the EXACT directed pair (from_currency->to_currency).
No inverse-rate synthesis. Fail-closed: missing rate -> None (caller keeps
foreign debits at face value with a note, and excludes foreign credits).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from affordai.finance.money import convert_amount, parse_amount
from affordai.ingestion import read_table


class RateTable:
    def __init__(self, rate_rows: list[dict]) -> None:
        index: dict[tuple[str, str], list[tuple[date, Decimal]]] = {}
        for r in rate_rows:
            series = index.setdefault(
                (r["from_currency"].strip(), r["to_currency"].strip()), []
            )
            series.append((r["rate_date"], r["rate"]))
        for series in index.values():
            series.sort()
        self._index = index

    def rate_on(self, from_cur: str, to_cur: str, day: date) -> Decimal | None:
        if from_cur == to_cur:
            return Decimal(1)
        series = self._index.get((from_cur, to_cur))
        if not series:
            return None
        best: Decimal | None = None
        for rate_date, rate in series:
            if rate_date <= day:
                best = rate
            else:
                break
        return best

    def to_home(
        self, amount: Decimal, currency: str, home: str, day: date
    ) -> Decimal | None:
        if currency == home:
            return amount
        rate = self.rate_on(currency, home, day)
        if rate is None:
            return None
        return convert_amount(amount, rate)


def load_rates(path: str) -> RateTable:
    from affordai.ingestion import require_date

    rows = read_table(path, ["rate_date", "from_currency", "to_currency", "rate"])
    parsed = []
    for r in rows:
        try:
            rate = parse_amount(r["rate"])
        except ValueError:
            rate = None
        if rate is None or rate <= 0:
            continue
        parsed.append(
            {
                "rate_date": require_date(r["rate_date"], "exchange_rates.rate_date"),
                "from_currency": r["from_currency"].strip(),
                "to_currency": r["to_currency"].strip(),
                "rate": rate,
            }
        )
    return RateTable(parsed)
