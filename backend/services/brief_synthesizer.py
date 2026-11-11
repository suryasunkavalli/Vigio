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
from backend.config import PLATFORM_VERSION
from backend.services.anthropic_service import (
    create_message,
    get_anthropic_model,
    parse_json_response,
    require_json_fields,
)

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """You are a senior pharmacovigilance medical reviewer synthesizing a Case Intelligence Brief.

Vigio reads every case through three lenses. You have been provided with:
1. Extracted case entities (ICH E2A four elements and clinical detail)
2. Regulatory Safety lens (validity, seriousness, listedness, reporting trigger)
3. Clinical Safety lens (case-level medical review, proposed WHO-UMC causality, follow-up questions, literature)
4. Population Safety & Evidence Generation lens (FAERS disproportionality, subgroups, evidence gaps)

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
   (draw on missing information, the follow-up questions and the evidence gaps)

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

LENS 1 — REGULATORY SAFETY:
- Validity: {regulatory.validity_status}
- Four Elements: {json.dumps(regulatory.four_element_check)}
- Missing elements: {entities.missing_elements}
- Seriousness: {regulatory.seriousness}
- Seriousness criteria: {regulatory.seriousness_criteria_met}
- Expectedness: {regulatory.expectedness} ({regulatory.label_source})
- Expectedness basis: {regulatory.expectedness_basis}
- Reasonable possibility: {regulatory.reportability_causality}
- Reporting Trigger: {regulatory.reporting_trigger}
- Trigger rationale: {regulatory.reporting_trigger_rationale}
- Day Zero: {regulatory.day_zero}
- Regulatory notes: {regulatory.regulatory_notes}

LENS 2 — CLINICAL SAFETY:
- Clinical summary: {clinical.case_clinical_summary}
- Time to onset: {clinical.time_to_onset_assessment}
- Dose/exposure: {clinical.dose_exposure_assessment}
- Dechallenge/rechallenge: {clinical.dechallenge_rechallenge_assessment}
- Risk factors: {clinical.risk_factors}
- Alternative causes: {clinical.alternative_causes}
- Proposed causality (WHO-UMC): {clinical.causality.category.value} — {clinical.causality.rationale}
- Follow-up questions: {clinical.follow_up_questions}
- Mechanism: {clinical.mechanistic_summary}
- PubMed references retrieved: {len(clinical.pubmed_references)}

LENS 3 — POPULATION SAFETY & EVIDENCE GENERATION:
- Signal summary: {population.signal_summary}
- FAERS reports (drug+event): {population.faers_signal.report_count if population.faers_signal else 'N/A'}
- ROR (95% CI): {population.faers_signal.reporting_odds_ratio if population.faers_signal else 'N/A'} ({population.faers_signal.ror_ci_lower if population.faers_signal else ''}–{population.faers_signal.ror_ci_upper if population.faers_signal else ''})
- Classification: {population.faers_signal.signal_strength if population.faers_signal else 'N/A'}
- Evidence gaps: {[g.question for g in population.evidence_gaps]}

CASE ENTITIES:
- Patient: {entities.patient}, Age: {entities.patient_age}, Sex: {entities.patient_sex}
- Reporter: {entities.reporter} ({entities.reporter_type})
- Suspect Product: {entities.suspect_product} — {entities.suspect_product_dose}
- Indication: {entities.suspect_product_indication}
- Adverse Event: {entities.adverse_event}
- Onset: {entities.adverse_event_onset}
- Outcome: {entities.adverse_event_outcome}

Synthesize the Case Intelligence Brief now."""

    response = create_message(
        client,
        max_tokens=1500,
        system=SYNTHESIS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}]
    )

    data = parse_json_response(response, "brief synthesis")
    require_json_fields(
        data,
        {
            "executive_summary", "recommended_action",
            "recommended_action_rationale", "key_uncertainties",
        },
        "brief synthesis",
    )

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
        "model": get_anthropic_model(),
        "lenses_computed": ["regulatory_safety", "clinical_safety", "population_safety_evidence"],
        "source_file": source_filename,
        "platform": PLATFORM_VERSION
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
