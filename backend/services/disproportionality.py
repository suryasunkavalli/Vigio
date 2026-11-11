"""Disproportionality statistics shared by the Population lens and FAERS search."""

import math
from backend.config import SDR_MIN_CASES, ROR_STRONG, ROR_MODERATE


def calculate_ror(a: int, drug_total: int, event_total: int, n_total: int):
    """
    Reporting odds ratio with 95% CI.
        a = drug + event          b = drug, other events
        c = other drugs + event   d = other drugs, other events
    Returns (ror, ci_lower, ci_upper) or (None, None, None) if any cell is empty.
    """
    b = drug_total - a
    c = event_total - a
    d = n_total - a - b - c
    if min(a, b, c, d) <= 0:
        return None, None, None
    ror = (a / b) / (c / d)
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    lo, hi = math.exp(math.log(ror) - 1.96 * se), math.exp(math.log(ror) + 1.96 * se)
    return round(ror, 2), round(lo, 2), round(hi, 2)


def classify_signal(a: int, ror, ci_lower) -> tuple[bool, str]:
    """SDR when a >= SDR_MIN_CASES and the CI lower bound is above 1; strength by ROR."""
    if a < SDR_MIN_CASES:
        return False, f"Insufficient data (fewer than {SDR_MIN_CASES} reports)"
    if ror is None or ci_lower is None:
        return False, "Unable to calculate"
    if ci_lower <= 1:
        return False, "No disproportionate reporting (CI includes 1)"
    if ror >= ROR_STRONG:
        return True, f"Strong (ROR ≥ {ROR_STRONG:g})"
    if ror >= ROR_MODERATE:
        return True, f"Moderate (ROR {ROR_MODERATE:g}–{ROR_STRONG:g})"
    return True, f"Weak (ROR < {ROR_MODERATE:g})"


def data_confidence(a: int) -> str:
    """Heuristic confidence in the disproportionality estimate, by number of drug-event reports."""
    if a >= 100:
        return "High"
    if a >= 20:
        return "Moderate"
    return "Low"


def signal_row(a: int, drug_total: int, event_total: int, n_total: int) -> dict:
    ror, lo, hi = calculate_ror(a, drug_total, event_total, n_total)
    is_sdr, strength = classify_signal(a, ror, lo)
    return {"reports": a, "event_total": event_total, "ror": ror, "ci_lower": lo, "ci_upper": hi,
            "is_sdr": is_sdr, "strength": strength, "confidence": data_confidence(a)}
