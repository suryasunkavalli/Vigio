"""
Layer 1: Regulatory Intelligence
- ICH E2A four-element validity
- Seriousness assessment (21 CFR 312.32)
- 7-day vs 15-day reporting trigger
- Expectedness determination
"""

import logging
from anthropic import Anthropic
from backend.models.case import (
    CaseEntities, RegulatoryIntelligence,
    Seriousness, ReportingTrigger, ValidityStatus, Expectedness
)
from backend.services.anthropic_service import (
    create_message, parse_json_response, require_json_fields
)

logger = logging.getLogger(__name__)

REGULATORY_SYSTEM_PROMPT = """You are a pharmacovigilance regulatory expert with deep knowledge of:
- ICH E2A guidelines (Individual Case Safety Report data elements)
- 21 CFR 312.32 (IND Safety Reports)
- FDA and EMA expedited reporting requirements
- ICH E2B(R3) data standards

Analyze the case and determine:

1. VALIDITY: Are all four ICH E2A elements present?
   Elements: identifiable patient, identifiable reporter, suspect product, adverse event

2. SERIOUSNESS: Under 21 CFR 312.32, is this serious?
   Criteria: Fatal, Life-threatening, Hospitalization, Disability/incapacity, Congenital anomaly, Medically significant

3. REPORTING TRIGGER:
   - 7-Day: Fatal or life-threatening AND unexpected (unlisted in IB/USPI)
   - 15-Day: Serious AND unexpected (other than fatal/life-threatening)
   - Periodic: Serious but expected, or non-serious
   - Note: Day 0 is the date the sponsor first receives information that COULD constitute a valid case

4. EXPECTEDNESS: Is the adverse event listed in the product's labeling (IB or USPI)?
   If the label is not available, state Unknown.

Return ONLY valid JSON:
{
  "validity_status": "Valid" | "Incomplete" | "Invalid",
  "four_element_check": {
    "patient": "present" | "absent" | "uncertain",
    "reporter": "present" | "absent" | "uncertain",
    "suspect_product": "present" | "absent" | "uncertain",
    "adverse_event": "present" | "absent" | "uncertain"
  },
  "seriousness": "Fatal" | "Life-Threatening" | "Hospitalization / Prolonged Hospitalization" | "Disability / Incapacity" | "Congenital Anomaly" | "Medically Significant" | "Non-Serious",
  "seriousness_criteria_met": ["list of applicable 21 CFR 312.32 criteria"],
  "expectedness": "Expected (Listed)" | "Unexpected (Unlisted)" | "Unknown / Label Not Available",
  "expectedness_basis": "explanation of expectedness determination",
  "reporting_trigger": "7-Day (Fatal/Life-Threatening Unexpected)" | "15-Day (Serious Unexpected)" | "Periodic (Expected or Non-Serious)" | "Not Applicable",
  "reporting_trigger_rationale": "explanation of trigger logic applied",
  "day_zero": "date string if determinable, else null",
  "regulatory_notes": "any additional regulatory considerations",
  "citations": ["ICH E2A (1994)", "21 CFR 312.32", "relevant guidance documents"]
}"""


def assess_regulatory_intelligence(
    entities: CaseEntities,
    narrative: str,
    client: Anthropic
) -> RegulatoryIntelligence:
    """
    Perform regulatory intelligence assessment.
    Applies ICH E2A, 21 CFR 312.32, and reporting trigger logic.
    """
    logger.info(f"Running regulatory intelligence for case {entities.case_id}")

    context = f"""Case Narrative:
{narrative[:6000]}

Extracted Entities:
- Patient: {entities.patient} (Age: {entities.patient_age}, Sex: {entities.patient_sex})
- Reporter: {entities.reporter} ({entities.reporter_type})
- Suspect Product: {entities.suspect_product} — {entities.suspect_product_dose}
- Indication: {entities.suspect_product_indication}
- Adverse Event: {entities.adverse_event}
- Onset: {entities.adverse_event_onset}
- Outcome: {entities.adverse_event_outcome}"""

    response = create_message(
        client,
        max_tokens=1500,
        system=REGULATORY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}]
    )

    data = parse_json_response(response, "regulatory intelligence")
    require_json_fields(
        data,
        {
            "validity_status", "four_element_check", "seriousness",
            "seriousness_criteria_met", "expectedness", "expectedness_basis",
            "reporting_trigger", "reporting_trigger_rationale", "day_zero",
            "regulatory_notes", "citations",
        },
        "regulatory intelligence",
    )

    return RegulatoryIntelligence(
        validity_status=data.get("validity_status", ValidityStatus.INVALID),
        four_element_check=data.get("four_element_check", {}),
        seriousness=data.get("seriousness", Seriousness.MEDICALLY_SIGNIFICANT),
        seriousness_criteria_met=data.get("seriousness_criteria_met", []),
        expectedness=data.get("expectedness", Expectedness.UNKNOWN),
        expectedness_basis=data.get("expectedness_basis", ""),
        reporting_trigger=data.get("reporting_trigger", ReportingTrigger.FIFTEEN_DAY),
        reporting_trigger_rationale=data.get("reporting_trigger_rationale", ""),
        day_zero=data.get("day_zero"),
        regulatory_notes=data.get("regulatory_notes", ""),
        citations=data.get("citations", ["ICH E2A (1994)", "21 CFR 312.32"])
    )
