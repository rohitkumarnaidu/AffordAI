"""Deterministic message interpreter (E0 baseline, no model calls).

Emits TYPED FACTS only (kind + normalized value + provenance). The rule
engine never reads raw message text, so embedded instructions
("ignore the minimum", "approve anyway") cannot override financial rules:
no pattern maps instruction-like text to any fact kind.
"""
from __future__ import annotations

import re
from decimal import Decimal

from affordai.evidence.evidence_registry import Evidence

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("cancel", re.compile(r"\bcancel(?:led|lation|ling)?\b", re.I)),
    ("settle", re.compile(r"\b(?:settled|settlement|paid in full|completed payment)\b", re.I)),
    ("confirm", re.compile(r"\b(?:confirm(?:ed|ation)?|received|verified|processed)\b", re.I)),
    ("delay", re.compile(r"\b(?:delay(?:ed)?|postpone(?:d)?|defer(?:red)?|move (?:it )?to)\b", re.I)),
]

# Payment-preference signals (advisory, deterministic; profile remains authoritative)
_PREF_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("installments", re.compile(r"\b(?:only(?:\s+in)?\s+installments?|prefer\s+installments?|installment\s+only|pay\s+in\s+installments?)\b", re.I)),
    ("partial_payment", re.compile(r"\b(?:only\s+partial|prefer\s+partial|split\s+payment|pay\s+part|partial\s+payment)\b", re.I)),
    ("full_payment", re.compile(r"\b(?:only\s+full|pay\s+in\s+full|prefer\s+full|full\s+payment(?:\s+only)?)\b", re.I)),
    ("wait", re.compile(r"\b(?:please\s+wait|hold\s+off|delay\s+purchase|wait\s+to\s+pay)\b", re.I)),
]

# NOTE: `payroll` deliberately excluded: payroll refs (EMP-0001, SER-0007)
# follow the word and poison amount capture. `pay` keeps (?![a-z]) guard.
# Gap allows verb phrases between keyword and number (e.g. Indonesian
# "Gaji bulanan Anda naik menjadi IDR 42750000" spans ~30 chars).
_AMOUNT_RE = re.compile(
    r"(?<![a-z])(?:amount|total|balance|pay|charge|salary|gaji|wage|upah)"
    r"(?![a-z])[^.\d]{0,40}?(?:EUR|USD|IDR|INR|ZAR|Rp|\$|€)?\s*([\d,]+(?:\.\d{1,2})?)",
    re.I,
)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# Request-level payroll messages (blank related_event_id) amend the user's
# scheduled salary when salary keywords are present; the pipeline links them
# to the earliest scheduled salary event in the window (documented).
SALARY_RE = re.compile(r"salary|gaji|payroll|\bpay\b|wage|upah", re.I)

# Sec 44 (3B): a bare year that continues as an ISO date (2025 in 2025-08-23)
# is a calendar fragment, never money. Checked against the text immediately
# following the captured number.
_ISO_DATE_TAIL_RE = re.compile(r"^-\d{2}-\d{2}\b")

# Sec 44 (3C): negation tokens. A state-changing keyword (cancel/settle/delay)
# preceded by negation within a short token window ("do not cancel", "belum
# dibatalkan") is a benign mention, not an instruction -- suppress the fact.
# Fail-closed direction: suppressing a true cancel keeps the outflow (safe).
_NEGATION_TOKENS = frozenset({
    "no", "not", "never", "without", "cannot",
    "tidak", "jangan", "belum", "bukan", "tanpa",
})
_NEGATION_TOKEN_RE = re.compile(r"[A-Za-z']+")
_NEGATION_WINDOW_TOKENS = 4
# Kinds whose facts can move money or dates (suppressed under negation).
# confirm/preference are advisory/evidence-only and keep current behavior.
_NEGATION_GATED_KINDS = frozenset({"cancel", "settle", "delay"})


def _is_negated(text: str, match_start: int) -> bool:
    """True iff a negation token appears just before ``match_start``."""
    prefix = text[:match_start]
    tokens = _NEGATION_TOKEN_RE.findall(prefix)[-_NEGATION_WINDOW_TOKENS:]
    for tok in tokens:
        low = tok.lower()
        if low in _NEGATION_TOKENS or low.endswith("n't"):
            return True
    return False


def _first_valid_amount(text: str):
    """First _AMOUNT_RE match that is not an ISO-date year fragment."""
    for m in _AMOUNT_RE.finditer(text):
        tail = text[m.end(1):m.end(1) + 6]
        if _ISO_DATE_TAIL_RE.match(tail):
            continue
        return m
    return None


def interpret(message: dict) -> list[Evidence]:
    """Extract typed facts from one loaded message row."""
    text = message.get("message_text") or ""
    base = dict(
        source_type="message",
        source_id=message["message_id"],
        request_id=message["request_id"],
        user_id=message["user_id"],
        event_id=message["related_event_id"],
        message_id=message["message_id"],
        confidence=Decimal("1.0"),
        method="deterministic",
    )
    facts: list[Evidence] = []
    for kind, rx in _PATTERNS:
        m = rx.search(text)
        if m:
            if kind in _NEGATION_GATED_KINDS and _is_negated(text, m.start()):
                continue  # benign/negated mention (Sec 44 3C), not a state change
            facts.append(Evidence(kind=kind, raw_value=text[:200], **base))
    amount = _first_valid_amount(text)
    # Emitted even without related_event_id: the pipeline links request-level
    # payroll amounts to scheduled salary; unlinked facts are ignored downstream.
    if amount:
        facts.append(
            Evidence(
                kind="amend_amount",
                raw_value=amount.group(0)[:200],
                normalized_value=amount.group(1).replace(",", ""),
                **base,
            )
        )
    dates = _DATE_RE.findall(text)
    if dates and message["related_event_id"]:
        facts.append(
            Evidence(
                kind="amend_date",
                raw_value=dates[0],
                normalized_value=dates[0],
                **base,
            )
        )
    # Payment preference (advisory, does not directly gate eligibility -- deterministic profile does)
    for pref_kind, rx in _PREF_PATTERNS:
        if rx.search(text):
            facts.append(
                Evidence(
                    kind="preference",
                    raw_value=text[:200],
                    normalized_value=pref_kind,
                    **base,
                )
            )
            break
    return facts
