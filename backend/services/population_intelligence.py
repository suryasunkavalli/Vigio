"""
Layer 3: Population Intelligence
- Queries OpenFDA (FAERS) for drug-event disproportionality
- Calculates reporting signal strength
- Provides background context
"""

import httpx
import math
import logging
from anthropic import Anthropic
from backend.models.case import CaseEntities, PopulationIntelligence, FAERSSignal

logger = logging.getLogger(__name__)

OPENFDA_BASE = "https://api.fda.gov/drug/event.json"


def query_faers_event_count(drug: str, event: str) -> int:
    """Count reports for drug + event combination in FAERS."""
    try:
        resp = httpx.get(
            OPENFDA_BASE,
            params={
                "search": f'patient.drug.medicinalproduct:"{drug}" AND patient.reaction.reactionmeddrapt:"{event}"',
                "limit": 1
            },
            timeout=10.0
        )
        if resp.status_code == 200:
            return resp.json().get("meta", {}).get("results", {}).get("total", 0)
        return 0
    except Exception as e:
        logger.warning(f"FAERS drug+event query failed: {e}")
        return 0


def query_faers_drug_total(drug: str) -> int:
    """Count all reports for the drug in FAERS."""
    try:
        resp = httpx.get(
            OPENFDA_BASE,
            params={
                "search": f'patient.drug.medicinalproduct:"{drug}"',
                "limit": 1
            },
            timeout=10.0
        )
        if resp.status_code == 200:
            return resp.json().get("meta", {}).get("results", {}).get("total", 0)
        return 0
    except Exception as e:
        logger.warning(f"FAERS drug total query failed: {e}")
        return 0


def calculate_ror(
    drug_event: int,
    drug_total: int,
    all_event_approx: int = 50000,
    all_reports_total: int = 29_000_000
) -> float | None:
    """
    Calculate Reporting Odds Ratio (ROR) — a standard FAERS disproportionality metric.
    ROR = (a/b) / (c/d)
    a = drug+event, b = drug without event, c = other drugs+event, d = other drugs without event
    """
    a = drug_event
    b = max(drug_total - drug_event, 1)
    c = max(all_event_approx - drug_event, 1)
    d = max(all_reports_total - drug_total - c, 1)

    if a == 0 or b == 0:
        return None
    return round((a / b) / (c / d), 2)


def signal_strength_label(ror: float | None, count: int) -> str:
    if count < 3:
        return "Insufficient Data (< 3 reports)"
    if ror is None:
        return "Unable to calculate"
    if ror >= 10:
        return "Strong Signal (ROR ≥ 10)"
    if ror >= 3:
        return "Moderate Signal (ROR 3-10)"
    if ror >= 1.5:
        return "Weak Signal (ROR 1.5-3)"
    return "No Disproportionate Signal (ROR < 1.5)"


def assess_population_intelligence(
    entities: CaseEntities,
    client: Anthropic
) -> PopulationIntelligence:
    """
    Query FAERS via OpenFDA, calculate ROR, and synthesize population signal.
    """
    logger.info(f"Running population intelligence for case {entities.case_id}")

    drug = (entities.suspect_product or "").split()[0]  # Use primary drug name
    event = entities.adverse_event or ""

    if not drug or not event:
        return PopulationIntelligence(
            signal_summary="Insufficient case data to perform population intelligence query.",
            population_notes="Drug name or adverse event term not identified in case."
        )

    # Query FAERS
    drug_event_count = query_faers_event_count(drug, event)
    drug_total_count = query_faers_drug_total(drug)

    ror = calculate_ror(drug_event_count, drug_total_count)
    strength = signal_strength_label(ror, drug_event_count)

    faers_signal = FAERSSignal(
        drug_name=drug,
        event_term=event,
        report_count=drug_event_count,
        total_drug_reports=drug_total_count,
        reporting_odds_ratio=ror,
        signal_strength=strength
    )

    # Synthesize context with Claude
    prompt = f"""Drug: {drug}
Adverse Event: {event}

FAERS Data:
- Reports for this drug + event combination: {drug_event_count:,}
- Total FAERS reports for this drug: {drug_total_count:,}
- Reporting Odds Ratio (ROR): {ror if ror else 'insufficient data'}
- Signal Strength: {strength}
- FAERS database: ~29 million reports (OpenFDA)

Provide:
1. A brief population signal summary (2-3 sentences) suitable for a regulatory reviewer
2. Background context on what is known about this drug's adverse event profile in the general population
3. Any caveats about FAERS data limitations relevant to this case

Be factual. Do not overstate the signal. Note that FAERS data is voluntary, subject to reporting bias, and does not establish causality."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=800,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    synthesis = response.content[0].text.strip()

    # Split into summary + notes
    lines = synthesis.split("\n")
    signal_summary = lines[0] if lines else synthesis
    population_notes = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

    return PopulationIntelligence(
        faers_signal=faers_signal,
        background_context=f"OpenFDA FAERS (29M+ reports): {drug_event_count:,} reports for {drug} + {event}. ROR: {ror or 'N/A'}. {strength}.",
        population_notes=population_notes,
        signal_summary=signal_summary
    )
