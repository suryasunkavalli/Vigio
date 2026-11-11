"""
Case Intelligence Brief Synthesizer.
Combines all three intelligence layers into a final structured brief
with an executive summary and recommended action.
"""

import json
import logging
from datetime import datetime
from uuid import uuid4
from anthropic import Anthropic
from backend.models.case import (
    CaseEntities, RegulatoryIntelligence, ClinicalIntelligence,
    PopulationIntelligence, CaseIntelligenceBrief, HumanConfirmation,
    RecommendedAction, ReportingTrigger, ValidityStatus
)

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """You are a senior pharmacovigilance medical reviewer synthesizing a Case Intelligence Brief.

You have been provided with:
1. Extracted case entities (ICH E2A four elements)
2. Regulatory intelligence (validity, seriousness, reporting trigger)
3. Clinical intelligence (PubMed mechanistic evidence)
4. Population intelligence (FAERS signal)

Your task is to produce:
1. An executive_summary (3-5 sentences): the key facts a reviewer needs to decide on this case
2. A recommended_action: one of:
   - "Submit 7-Day Expedited Report"
   - "Submit 15-Day Expedited Report"
   - "Include in Periodic Safety Report"
   - "Obtain Follow-Up Information"
   - "No Regulatory Action Required"
   - "Senior Medical Review Required"
3. recommended_action_rationale (2-3 sentences): why this action is recommended
4. key_uncertainties (list of strings): 2-4 uncertainties the reviewer should be aware of

Important:
- This is intelligence, not a determination. Do not make legal or regulatory claims.
- Flag missing information clearly.
- Be conservative when data is incomplete.
- Cite the regulatory trigger explicitly in the rationale.

Return ONLY valid JSON:
{
  "executive_summary": "...",
  "recommended_action": "...",
  "recommended_action_rationale": "...",
  "key_uncertainties": ["...", "..."]
}"""


def determine_recommended_action(regulatory: RegulatoryIntelligence) -> RecommendedAction:
    """
    Derive recommended action from regulatory intelligence.
    Used as fallback if Claude synthesis fails.
    """
    if regulatory.validity_status == ValidityStatus.INVALID:
        return RecommendedAction.NO_ACTION

    if regulatory.validity_status == ValidityStatus.INCOMPLETE:
        return RecommendedAction.FOLLOW_UP

    trigger = regulatory.reporting_trigger
    if trigger == ReportingTrigger.SEVEN_DAY:
        return RecommendedAction.EXPEDITED_7DAY
    elif trigger == ReportingTrigger.FIFTEEN_DAY:
        return RecommendedAction.EXPEDITED_15DAY
    elif trigger == ReportingTrigger.PERIODIC:
        return RecommendedAction.PERIODIC
    else:
        return RecommendedAction.REVIEW_NEEDED


def synthesize_brief(
    entities: CaseEntities,
    regulatory: RegulatoryIntelligence,
    clinical: ClinicalIntelligence,
    population: PopulationIntelligence,
    client: Anthropic,
    source_filename: str = "",
    processing_duration: float = None
) -> CaseIntelligenceBrief:
    """
    Combine all three intelligence layers into a Case Intelligence Brief.
    """
    logger.info(f"Synthesizing Case Intelligence Brief for case {entities.case_id}")

    # Build synthesis context
    context = f"""Case ID: {entities.case_id}

LAYER 1 — REGULATORY INTELLIGENCE:
- Validity: {regulatory.validity_status}
- Four Elements: {json.dumps(regulatory.four_element_check)}
- Missing elements: {entities.missing_elements}
- Seriousness: {regulatory.seriousness}
- Seriousness criteria: {regulatory.seriousness_criteria_met}
- Expectedness: {regulatory.expectedness}
- Expectedness basis: {regulatory.expectedness_basis}
- Reporting Trigger: {regulatory.reporting_trigger}
- Trigger rationale: {regulatory.reporting_trigger_rationale}
- Day Zero: {regulatory.day_zero}
- Regulatory notes: {regulatory.regulatory_notes}
- Citations: {regulatory.citations}

LAYER 2 — CLINICAL INTELLIGENCE:
- Mechanistic summary: {clinical.mechanistic_summary}
- Clinical plausibility: {clinical.clinical_plausibility}
- PubMed references found: {len(clinical.pubmed_references)}
- Label cross-reference: {clinical.label_cross_reference}
- Clinical notes: {clinical.clinical_notes}

LAYER 3 — POPULATION INTELLIGENCE:
- Signal summary: {population.signal_summary}
- FAERS reports: {population.faers_signal.report_count if population.faers_signal else 'N/A'}
- Signal strength: {population.faers_signal.signal_strength if population.faers_signal else 'N/A'}
- ROR: {population.faers_signal.reporting_odds_ratio if population.faers_signal else 'N/A'}
- Background context: {population.background_context}

CASE ENTITIES:
- Patient: {entities.patient}, Age: {entities.patient_age}, Sex: {entities.patient_sex}
- Reporter: {entities.reporter} ({entities.reporter_type})
- Suspect Product: {entities.suspect_product} — {entities.suspect_product_dose}
- Indication: {entities.suspect_product_indication}
- Adverse Event: {entities.adverse_event}
- Onset: {entities.adverse_event_onset}
- Outcome: {entities.adverse_event_outcome}

Synthesize the Case Intelligence Brief now."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
        system=SYNTHESIS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}]
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Brief synthesis JSON parse error: {e}")
        data = {}

    # Map recommended_action string to enum
    raw_action = data.get("recommended_action", "")
    action_enum = RecommendedAction.REVIEW_NEEDED
    for member in RecommendedAction:
        if member.value == raw_action:
            action_enum = member
            break
    else:
        # Fallback: derive from regulatory layer
        action_enum = determine_recommended_action(regulatory)

    # Build audit trail entry for generation
    audit_entry = {
        "event": "brief_generated",
        "timestamp": datetime.utcnow().isoformat(),
        "model": "claude-opus-4-5",
        "layers_computed": ["regulatory", "clinical", "population"],
        "source_file": source_filename,
        "platform": "Verix MVP 0.1"
    }

    return CaseIntelligenceBrief(
        brief_id=str(uuid4()),
        case_id=entities.case_id,
        entities=entities,
        regulatory=regulatory,
        clinical=clinical,
        population=population,
        executive_summary=data.get("executive_summary", "Brief synthesis failed — manual review required."),
        recommended_action=action_enum,
        recommended_action_rationale=data.get("recommended_action_rationale", ""),
        key_uncertainties=data.get("key_uncertainties", []),
        human_confirmation=HumanConfirmation(),
        audit_trail=[audit_entry],
        source_pdf_filename=source_filename,
        processing_duration_seconds=processing_duration
    )
