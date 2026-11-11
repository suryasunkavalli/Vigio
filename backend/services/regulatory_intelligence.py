"""
Lens 1: Regulatory Safety
Question: what are we required to assess, document and report?

- ICH E2A four-element validity
- Seriousness (21 CFR 312.32 / 314.80)
- Expectedness / listedness against a reference label, when one is loaded
- Reasonable-possibility causality for expedited reporting
- Reporting context (IND vs postmarketing) and 7-day / 15-day / periodic trigger
"""

import logging
from pathlib import Path
from anthropic import Anthropic
from backend.models.case import (
    CaseEntities, RegulatoryIntelligence,
    Seriousness, ReportingTrigger, ValidityStatus, Expectedness
)
from backend.services.anthropic_service import (
    create_message,
    parse_json_response,
    require_json_fields,
)

logger = logging.getLogger(__name__)

# Reference labels (USPI, SmPC or Investigator's Brochure excerpts) as plain text:
#   backend/labels/<generic name>.txt   e.g. backend/labels/warfarin.txt
LABELS_DIR = Path(__file__).resolve().parent.parent / "labels"
MAX_LABEL_CHARS = 20000

REGULATORY_SYSTEM_PROMPT = """You are a pharmacovigilance regulatory expert with deep knowledge of:
- ICH E2A (clinical safety data management, expedited reporting)
- 21 CFR 312.32 (IND safety reporting), 21 CFR 314.80 and 600.80 (postmarketing reporting)
- ICH E2B(R3) data standards

Analyze the case and determine:

1. VALIDITY: Are all four ICH E2A elements present?
   Elements: identifiable patient, identifiable reporter, suspect product, adverse event

2. SERIOUSNESS: Under 21 CFR 312.32, is this serious?
   Criteria: Fatal, Life-threatening, Hospitalization, Disability/incapacity, Congenital anomaly, Medically significant

3. EXPECTEDNESS / LISTEDNESS:
   - If a REFERENCE LABEL is provided, decide whether the event (including its nature, severity
     and specificity) is listed in it, and quote or closely paraphrase the relevant label section.
   - If no label is provided, return "Unknown / Label Not Available". Do not rely on memory of the label.

4. REASONABLE POSSIBILITY: For expedited reporting, is there a reasonable possibility the
   product caused the event (i.e. is it a suspected adverse reaction)? Explain briefly.

5. REPORTING CONTEXT AND TRIGGER:
   First decide the context and cite the matching regulation:
   - Clinical trial / IND case -> 21 CFR 312.32:
       7-Day: fatal or life-threatening AND unexpected AND suspected adverse reaction
       15-Day: serious AND unexpected AND suspected adverse reaction
   - Postmarketing case (spontaneous or solicited, marketed product) -> 21 CFR 314.80 (drugs)
     or 21 CFR 600.80 (biologics): 15-day Alert report if serious AND unexpected;
     otherwise periodic. There is no 7-day category postmarketing.
   - Periodic: expected, or non-serious.
   - If expectedness is Unknown, state which trigger would apply if the event is unexpected.
   - Day 0 is the date the company first receives the minimum information for a valid case.

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
  "expectedness_basis": "explanation, citing the label section if a label was provided",
  "reportability_causality": "reasonable-possibility assessment for reporting purposes",
  "reporting_trigger": "7-Day (Fatal/Life-Threatening Unexpected)" | "15-Day (Serious Unexpected)" | "Periodic (Expected or Non-Serious)" | "Not Applicable",
  "reporting_trigger_rationale": "explanation of trigger logic applied",
  "day_zero": "date string if determinable, else null",
  "regulatory_notes": "any additional regulatory considerations",
  "citations": ["ICH E2A (1994)", "21 CFR 312.32", "other guidance actually relied on"]
}"""


def find_reference_label(drug: str | None) -> tuple[str, str]:
    """Return (label_text, label_source) for the suspect product, or ("", reason)."""
    if not drug:
        return "", "No suspect product identified."
    if LABELS_DIR.exists():
        drug_lower = drug.lower()
        for path in sorted(LABELS_DIR.glob("*.txt")):
            if path.stem.lower() in drug_lower:
                text = path.read_text(encoding="utf-8", errors="ignore")[:MAX_LABEL_CHARS]
                return text, f"Reference label loaded from labels/{path.name}"
    return "", f"No reference label loaded for {drug}. Add labels/<generic name>.txt to assess listedness."


def _enum_or(enum_cls, value, default):
    for member in enum_cls:
        if member.value == value:
            return member
    return default


def assess_regulatory_intelligence(
    entities: CaseEntities,
    narrative: str,
    client: Anthropic
) -> RegulatoryIntelligence:
    """Apply ICH E2A, 21 CFR 312.32, listedness and reporting-trigger logic."""
    logger.info(f"Running Regulatory Safety lens for case {entities.case_id}")

    label_text, label_source = find_reference_label(entities.suspect_product)
    label_block = (
        f"REFERENCE LABEL ({label_source}):\n{label_text}"
        if label_text else "REFERENCE LABEL: none provided."
    )

    context = f"""Case Narrative:
{narrative[:8000]}

Extracted Entities:
- Patient: {entities.patient} (Age: {entities.patient_age}, Sex: {entities.patient_sex})
- Reporter: {entities.reporter} ({entities.reporter_type})
- Suspect Product: {entities.suspect_product} - {entities.suspect_product_dose}
- Indication: {entities.suspect_product_indication}
- Adverse Event: {entities.adverse_event}
- Onset: {entities.adverse_event_onset}
- Outcome: {entities.adverse_event_outcome}

{label_block}"""

    response = create_message(
        client,
        max_tokens=2000,
        system=REGULATORY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}]
    )

    data = parse_json_response(response, "regulatory lens")
    require_json_fields(
        data,
        {
            "validity_status", "four_element_check", "seriousness",
            "seriousness_criteria_met", "expectedness", "expectedness_basis",
            "reportability_causality", "reporting_trigger",
            "reporting_trigger_rationale", "day_zero", "regulatory_notes", "citations",
        },
        "regulatory lens",
    )

    expectedness = _enum_or(Expectedness, data.get("expectedness"), Expectedness.UNKNOWN)
    if not label_text:
        # Never claim listedness without a label in hand.
        expectedness = Expectedness.UNKNOWN

    return RegulatoryIntelligence(
        validity_status=_enum_or(ValidityStatus, data.get("validity_status"), ValidityStatus.INCOMPLETE),
        four_element_check=data.get("four_element_check", {}),
        seriousness=_enum_or(Seriousness, data.get("seriousness"), Seriousness.MEDICALLY_SIGNIFICANT),
        seriousness_criteria_met=data.get("seriousness_criteria_met", []),
        expectedness=expectedness,
        expectedness_basis=data.get("expectedness_basis", "") if label_text else label_source,
        label_source=label_source,
        reportability_causality=data.get("reportability_causality", ""),
        reporting_trigger=_enum_or(ReportingTrigger, data.get("reporting_trigger"), ReportingTrigger.FIFTEEN_DAY),
        reporting_trigger_rationale=data.get("reporting_trigger_rationale", ""),
        day_zero=data.get("day_zero"),
        regulatory_notes=data.get("regulatory_notes", ""),
        citations=data.get("citations", ["ICH E2A (1994)", "21 CFR 312.32"])
    )
