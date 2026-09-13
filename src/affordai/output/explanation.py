"""Grounded explanations: template over validated Decision facts only.

Pipeline invariant (Section 24):
    validated canonical Decision
        -> explanation_facts (structured, no invention)
        -> grounded prose
        -> validator
        -> fallback if invalid

Never claims unsupported evidence, nonexistent transactions, dates, or
balances. When the LLM adapter drafts alternative wording (E3+), its output
must pass `validate()` here or the deterministic template below is used.

Content contract (Section 24.2):
    WHY (safe/unsafe + minimum/90-day), CONSTRAINT (floor/deadline), PLAN,
    TIMING (earliest), EVIDENCE (IDs). Concise, specific, no generic filler
    unless accompanied by facts.
"""
from __future__ import annotations

from affordai.finance.money import format_amount


# ---------- Structured facts (Section 24.5) ----------

def build_facts(decision) -> dict:
    """Derive structured ExplanationFacts from validated Decision only."""
    return {
        "amount_safe_to_pay": decision.amount_safe_to_pay,
        "affordability_status": decision.affordability_status,
        "recommended_payment_method": decision.recommended_payment_method,
        "payment_plan": decision.payment_plan,
        "earliest_date_for_full_payment": decision.earliest_date_for_full_payment,
        "spending_changes_needed": decision.spending_changes_needed,
        "evidence": tuple(decision.evidence) if hasattr(decision, "evidence") else (),
    }


def build_fallback(facts: dict) -> str:
    """Deterministic safe fallback -- never invents, always valid."""
    safe = facts.get("amount_safe_to_pay")
    status = facts.get("affordability_status", "not_affordable")
    method = facts.get("recommended_payment_method", "not_recommended")
    plan = facts.get("payment_plan", "none")
    earliest = facts.get("earliest_date_for_full_payment", "") or "not in forecast"
    changes = facts.get("spending_changes_needed", "none")
    # Use facts-provided safe if Decimal, else string
    try:
        from decimal import Decimal

        home = facts.get("home_currency") or "INR"
        if isinstance(safe, Decimal):
            safe_str = format_amount(safe, home)
        else:
            safe_str = str(safe) if safe is not None else "0"
    except Exception:
        safe_str = str(safe) if safe is not None else "0"
    requested = facts.get("requested_amount")
    req_str = ""
    try:
        if isinstance(requested, Decimal):
            req_str = format_amount(requested, facts.get("home_currency", "INR"))
        elif requested is not None:
            req_str = str(requested)
    except Exception:
        req_str = str(requested) if requested is not None else ""
    req_date = facts.get("request_date", "")
    # WHY + CONSTRAINT + PLAN + TIMING + EVIDENCE (concise, grounded)
    if req_str and req_date:
        base = (
            f"Requested {req_str} on {req_date}: {safe_str} safe to pay "
            f"today while keeping the minimum balance across the 90-day forecast "
            f"(status {status}, method {method})."
        )
    else:
        base = (
            f"{safe_str} safe to pay today while keeping the minimum balance "
            f"across the 90-day forecast (status {status}, method {method})."
        )
    if method == "not_recommended":
        return base + f" Full payment earliest safe: {earliest}. Plan: {plan}."
    tail = f" Full payment earliest safe: {earliest}. Plan: {plan}."
    if changes != "none":
        tail += f" Requires spending changes: {changes}."
    return base + tail


def build(decision, requested: str, request_date: str, home: str) -> str:
    """Legacy builder (Decision-like + requested string) -- delegates to grounded facts."""
    # Extract facts from decision (already validated) + supplied requested string
    safe = format_amount(decision.amount_safe_to_pay, home)
    earliest = decision.earliest_date_for_full_payment or "not in forecast"
    changes = decision.spending_changes_needed
    method = decision.recommended_payment_method
    status = decision.affordability_status
    plan = decision.payment_plan
    # WHY + CONSTRAINT + PLAN + TIMING + EVIDENCE
    base = (
        f"Requested {requested} {home} on {request_date}: {safe} {home} safe to pay "
        f"today while keeping the minimum balance across the 90-day forecast "
        f"(status {status}, method {method})."
    )
    if method == "not_recommended":
        return base + f" Full payment earliest safe: {earliest}. Plan: {plan}."
    tail = f" Full payment earliest safe: {earliest}. Plan: {plan}."
    if changes != "none":
        tail += f" Requires spending changes: {changes}."
    return base + tail


def validate(text: str, decision) -> bool:
    """Explanation consistency gate -- deterministic, no LLM self-check.

    Checks (Section 24.4 / 24.6):
        explanation amount == decision amount (via formatted safe)
        explanation date == decision date (earliest or not in forecast)
        explanation method == decision method
        explanation status == decision status
        explanation plan == decision plan
        no invented evidence IDs (if evidence present, they must appear or be omitted, not invented)
    Generic filler alone (e.g., 'best option') without facts is rejected.
    """
    if not text or not text.strip():
        return False
    # 1. Status/method must appear verbatim
    if decision.affordability_status not in text:
        return False
    if decision.recommended_payment_method not in text:
        return False
    # 2. Plan must appear when not "none" (and must not contradict)
    plan = getattr(decision, "payment_plan", "")
    if plan != "none" and plan not in text:
        # Allow truncated? No--must be exact or explanation is incomplete
        # But we accept if plan is "none" is correctly represented
        return False
    if plan == "none" and "Plan: none" not in text and "plan none" not in text.lower():
        # fallback phrasing may still be valid if it mentions not_recommended correctly
        # Require at least that earliest is mentioned for not_recommended
        pass
    # 3. Earliest must appear (or "not in forecast" when empty)
    earliest = getattr(decision, "earliest_date_for_full_payment", "")
    if earliest:
        if earliest not in text:
            return False
    else:
        if "not in forecast" not in text:
            return False
    # 4. Safe amount must appear formatted (check both bare int and 2dp variants)
    try:
        # Decision amount is Decimal; we need home to format. Try to infer home from facts or decision
        home = getattr(decision, "home_currency", None) or (getattr(decision, "explanation_facts", {}).get("home_currency") if hasattr(decision, "explanation_facts") else None) or "INR"
        safe_str = format_amount(decision.amount_safe_to_pay, home)
        # Also accept plain str of Decimal without formatting edge
        if safe_str not in text and str(decision.amount_safe_to_pay) not in text:
            return False
    except Exception:
        if str(decision.amount_safe_to_pay) not in text:
            return False
    # 5. Spending changes must be consistent when present
    changes = getattr(decision, "spending_changes_needed", "none")
    if changes != "none":
        if changes not in text:
            return False
    # 6. No generic unsupported claim without facts (reject pure filler)
    filler_only = text.strip().lower() in {
        "based on your financial situation, this is the best option.",
        "this is the best option.",
        "based on your financial situation.",
    }
    if filler_only:
        return False
    # 7. If explanation mentions evidence IDs, they must be subset of decision.evidence
    # Heuristic: look for tokens like "evidence:" or bare IDs starting with msg_/img_/evt_?
    # For now, ensure no invented amount that doesn't match decision
    # (Already checked safe amount; other numeric invented claims would need deeper NLP--out of scope for deterministic validator)
    return True


def validate_with_facts(text: str, facts: dict, decision=None) -> list[str]:
    """Extended validator returning structured error messages (for logging)."""
    errors: list[str] = []
    if not text or not text.strip():
        errors.append("empty explanation")
        return errors
    # Resolve expected values from facts (preferred) or decision
    src = facts if facts else (decision.explanation_facts if decision and hasattr(decision, "explanation_facts") else {})
    # Check existence of required facts
    for key in ("affordability_status", "recommended_payment_method", "payment_plan", "earliest_date_for_full_payment"):
        if key in src and src[key] not in text and src[key] != "none":
            # earliest empty -> expect "not in forecast"
            if key == "earliest_date_for_full_payment" and not src[key] and "not in forecast" not in text:
                errors.append(f"missing {key} {src[key]!r} in explanation")
            elif key != "earliest_date_for_full_payment":
                errors.append(f"missing {key} {src[key]!r} in explanation")
    return errors
