"""Authoritative currency engine (Checklist Section 12).

Single conversion path for the whole pipeline::

    raw foreign amount -> settlement-date rate -> Decimal math
    -> home-currency quantization -> ConversionTrace

Rate rule (assumption A1, see docs/specification.md section 2): latest
``exchange_rates.csv`` row ON or BEFORE the cash (settlement) date for the
EXACT directed pair (``from_currency -> to_currency``). No inverse-rate
synthesis: ``USD -> INR`` never implies ``INR -> USD``.

Fail-closed: a missing rate returns ``None`` (the caller keeps foreign
debits at face value with a note, and excludes foreign credits) — it never
substitutes ``0``, ``1``, or a live-market rate. There is NO network
dependency: only supplied rows are consulted (see ``RateTable``).

Determinism: currency codes are normalized (strip + upper); series are
sorted once at load; lookups are pure functions of
``(source, target, day)``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from affordai.finance.money import convert_amount, parse_amount, quantize_money
from affordai.ingestion import read_table

#: Home/event currencies observed in `financial_profiles.csv`. Unknown codes
#: fail closed (never silently substituted).
SUPPORTED_CURRENCIES = frozenset({"INR", "ZAR", "IDR", "USD", "EUR"})

#: Rounding policy applied once at the posting event (see money.py).
ROUNDING_POLICY = f"ROUND_HALF_UP/2dp(per-currency)"


class CurrencyError(Exception):
    """Base class for deterministic currency failures (never silent)."""


class UnsupportedCurrencyError(CurrencyError):
    """Currency code is blank, malformed, or outside SUPPORTED_CURRENCIES."""


class MissingRateError(CurrencyError):
    """No supplied rate row covers (pair, settlement date)."""


class DuplicateRateError(CurrencyError):
    """Conflicting supplied rows for the same (pair, rate_date)."""


def normalize_currency(code: object) -> str:
    """Normalize a currency code (strip + upper).

    Raises:
        UnsupportedCurrencyError: blank or non-string-parsable input.
    """
    if code is None:
        raise UnsupportedCurrencyError("blank currency (None)")
    text = str(code).strip().upper()
    if not text:
        raise UnsupportedCurrencyError("blank currency")
    return text


def validate_currency(code: object, what: str = "currency") -> str:
    """Normalize + check membership in SUPPORTED_CURRENCIES."""
    normalized = normalize_currency(code)
    if normalized not in SUPPORTED_CURRENCIES:
        raise UnsupportedCurrencyError(f"{what}: unsupported currency {normalized!r}")
    return normalized


@dataclass(frozen=True)
class RateLookup:
    """Traceable result of RateTable.get_rate (one authoritative lookup)."""

    source_currency: str
    target_currency: str
    settlement_date: date
    rate: Decimal
    rate_date: date
    rate_id: str  # f"{source}->{target}@{rate_date}"
    source_dataset: str
    same_currency: bool = False


@dataclass(frozen=True)
class ConversionTrace:
    """Full audit record for one conversion (Section 12.4 safety)."""

    source_currency: str
    target_currency: str
    source_amount: Decimal
    rate: Decimal | None
    rate_date: date | None
    converted_amount: Decimal | None  # quantized home amount; None on missing rate
    rounding_policy: str = ROUNDING_POLICY
    same_currency: bool = False
    reason: str = ""  # e.g. "same-currency path" | "missing-rate (fail-closed)"


class RateTable:
    """Repository over supplied dated rates (offline, deterministic)."""

    def __init__(
        self, rate_rows: list[dict], source_dataset: str = "exchange_rates.csv"
    ) -> None:
        index: dict[tuple[str, str], list[tuple[date, Decimal]]] = {}
        seen: dict[tuple[str, str, date], Decimal] = {}
        deduped = 0
        for r in rate_rows:
            pair = (normalize_currency(r["from_currency"]), normalize_currency(r["to_currency"]))
            day = r["rate_date"]
            rate = r["rate"]
            if not isinstance(day, date) or not isinstance(rate, Decimal):
                raise CurrencyError(f"malformed rate row: {r!r}")
            if rate <= 0 or not rate.is_finite():
                raise CurrencyError(f"non-positive rate row: {r!r}")
            key = (pair[0], pair[1], day)
            if key in seen:
                if seen[key] != rate:
                    raise DuplicateRateError(
                        f"conflicting rates for {pair[0]}->{pair[1]}@{day}: "
                        f"{seen[key]} vs {rate}"
                    )
                deduped += 1  # identical duplicate: collapse observably
                continue
            seen[key] = rate
            index.setdefault(pair, []).append((day, rate))
        for series in index.values():
            series.sort()
        self._index = index
        self.source_dataset = source_dataset
        self.duplicates_deduped = deduped

    # -- authoritative lookup -------------------------------------------------
    def get_rate(self, from_cur: str, to_cur: str, day: date) -> RateLookup:
        """Latest supplied row on-or-before ``day`` for the exact directed pair.

        Raises:
            UnsupportedCurrencyError: either code unsupported.
            MissingRateError: pair unknown, or all rows are after ``day``.
        """
        src = validate_currency(from_cur, "source_currency")
        tgt = validate_currency(to_cur, "target_currency")
        if not isinstance(day, date):
            raise CurrencyError(f"settlement date must be a date, got {day!r}")
        if src == tgt:
            return RateLookup(
                source_currency=src,
                target_currency=tgt,
                settlement_date=day,
                rate=Decimal(1),
                rate_date=day,
                rate_id=f"{src}->{tgt}@same",
                source_dataset=self.source_dataset,
                same_currency=True,
            )
        series = self._index.get((src, tgt))
        if not series:
            raise MissingRateError(f"unsupported pair {src}->{tgt} (no supplied rows)")
        best: tuple[date, Decimal] | None = None
        for rate_date, rate in series:
            if rate_date <= day:
                best = (rate_date, rate)
            else:
                break
        if best is None:
            raise MissingRateError(
                f"no {src}->{tgt} rate on-or-before {day} "
                f"(earliest supplied {series[0][0]})"
            )
        rate_date, rate = best
        return RateLookup(
            source_currency=src,
            target_currency=tgt,
            settlement_date=day,
            rate=rate,
            rate_date=rate_date,
            rate_id=f"{src}->{tgt}@{rate_date.isoformat()}",
            source_dataset=self.source_dataset,
        )

    # -- backwards-compatible wrappers (same semantics, normalized) -----------
    def rate_on(self, from_cur: str, to_cur: str, day: date) -> Decimal | None:
        """Legacy accessor: rate value or None (fail-closed). Case-insensitive."""
        try:
            src = normalize_currency(from_cur)
            tgt = normalize_currency(to_cur)
        except CurrencyError:
            return None
        if src == tgt:
            return Decimal(1)
        # NOTE: intentionally fail-closed (None) instead of raising, to keep
        # the historical call contract used by timeline + older tests.
        series = self._index.get((src, tgt))
        if not series:
            return None
        best: Decimal | None = None
        for rate_date, rate in series:
            if rate_date <= day:
                best = rate
            else:
                break
        return best

    def convert_to_home(
        self, amount: Decimal, currency: str, home: str, day: date
    ) -> tuple[Decimal | None, ConversionTrace]:
        """Authoritative conversion: foreign -> quantized home + trace.

        Same-currency is a no-FX path (no rate required). Missing rates
        return ``(None, trace)`` — never 0/1/market.
        """
        src = normalize_currency(currency)
        tgt = normalize_currency(home)
        if not isinstance(amount, Decimal):
            raise CurrencyError(f"source amount must be Decimal, got {amount!r}")
        if not amount.is_finite():
            raise CurrencyError(f"non-finite source amount {amount!r}")
        if src == tgt:
            trace = ConversionTrace(
                source_currency=src,
                target_currency=tgt,
                source_amount=amount,
                rate=Decimal(1),
                rate_date=day,
                converted_amount=amount,
                same_currency=True,
                reason="same-currency path (no FX)",
            )
            return amount, trace
        try:
            lookup = self.get_rate(src, tgt, day)
        except CurrencyError as exc:
            trace = ConversionTrace(
                source_currency=src,
                target_currency=tgt,
                source_amount=amount,
                rate=None,
                rate_date=None,
                converted_amount=None,
                reason=f"missing-rate (fail-closed): {exc}",
            )
            return None, trace
        raw = convert_amount(amount, lookup.rate)
        quantized = quantize_money(raw, tgt)
        trace = ConversionTrace(
            source_currency=src,
            target_currency=tgt,
            source_amount=amount,
            rate=lookup.rate,
            rate_date=lookup.rate_date,
            converted_amount=quantized,
            reason=f"rate {lookup.rate_id} from {self.source_dataset}",
        )
        return quantized, trace

    def to_home(
        self, amount: Decimal, currency: str, home: str, day: date
    ) -> Decimal | None:
        """Legacy accessor: quantized home amount or None (fail-closed)."""
        converted, _trace = self.convert_to_home(amount, currency, home, day)
        return converted


def load_rates(path: str) -> RateTable:
    """Load supplied rates offline. Skipped rows are recorded, never silent."""
    from affordai.ingestion import require_date

    rows = read_table(path, ["rate_date", "from_currency", "to_currency", "rate"])
    parsed = []
    skipped: list[str] = []
    for lineno, r in enumerate(rows, start=2):
        try:
            rate = parse_amount(r["rate"])
        except ValueError:
            skipped.append(f"line {lineno}: malformed rate {r['rate']!r}")
            continue
        if rate is None or rate <= 0:
            skipped.append(f"line {lineno}: non-positive rate {r['rate']!r}")
            continue
        try:
            rate_date = require_date(r["rate_date"], "exchange_rates.rate_date")
            src = normalize_currency(r["from_currency"])
            tgt = normalize_currency(r["to_currency"])
        except (CurrencyError, Exception) as exc:  # DatasetError subclasses Exception
            skipped.append(f"line {lineno}: {exc}")
            continue
        parsed.append(
            {"rate_date": rate_date, "from_currency": src, "to_currency": tgt, "rate": rate}
        )
    table = RateTable(parsed, source_dataset=path)
    table.load_skipped = skipped  # type: ignore[attr-defined]  # observability hook
    return table
