"""Exact monetary arithmetic for AffordAI.

Policy (locked from evidence):
- All money is :class:`decimal.Decimal`, constructed from STRINGS only.
- Never mix float into the money path (OpenSSF pyscg-0001; float cannot
  represent most decimal fractions exactly).
- Rounding mode is ROUND_HALF_UP (commercial convention), applied ONCE at
  posting events: FX conversion results and final output amounts.
- Scale is per-currency, seeded from observed `sample_requests.csv`
  formatting: 2dp amounts occur in every home currency INCLUDING IDR
  (e.g. ``15952906.67``), so all five currencies quantize to 2dp.
- Serialization: exact integers print bare (``25256``); non-integers print
  with exactly 2dp (``620.40``). This reproduces every sample format.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

CURRENCY_SCALE = {
    "INR": 2,
    "ZAR": 2,
    "IDR": 2,
    "USD": 2,
    "EUR": 2,
}

ROUNDING = ROUND_HALF_UP
_CALC_PRECISION = 28


def scale_for(currency: str) -> int:
    """Decimal places for a home currency. Unknown codes fail closed."""
    try:
        return CURRENCY_SCALE[currency]
    except KeyError:
        raise ValueError(f"unsupported currency: {currency!r}")


def parse_amount(raw: object) -> Decimal | None:
    """Parse a money string to Decimal.

    Returns None for blank/None (caller decides: image lookup, error, ...).
    NEVER returns 0 for blank input. Raises ValueError on malformed input,
    NaN, or infinities.
    """
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if text == "":
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"malformed amount: {raw!r}")
    if not value.is_finite():
        raise ValueError(f"non-finite amount: {raw!r}")
    return value


def quantize_money(value: Decimal, currency: str) -> Decimal:
    """Round once to the currency scale (posting event)."""
    places = scale_for(currency)
    quantum = Decimal(1).scaleb(-places)
    return value.quantize(quantum, rounding=ROUNDING)


def convert_amount(amount: Decimal, rate: Decimal) -> Decimal:
    """Multiply by an FX rate at full precision; caller quantizes."""
    with localcontext() as ctx:
        ctx.prec = _CALC_PRECISION
        return amount * rate


def format_amount(value: Decimal, currency: str) -> str:
    """Serialize per observed sample style: bare integers, else 2dp."""
    q = quantize_money(value, currency)
    if q == q.to_integral_value():
        return str(int(q))
    places = scale_for(currency)
    return f"{q:.{places}f}"
