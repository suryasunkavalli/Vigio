"""
Entity extraction service.
Uses Claude to extract the ICH E2A four elements plus the clinical detail the
Clinical Safety lens needs (timing, exposure, dechallenge/rechallenge, history,
concomitant medications, tests) from the raw case narrative.
"""

import logging
from anthropic import Anthropic
from backend.models.case import CaseEntities
from backend.services.anthropic_service import (
    create_message,
    parse_json_response,
    require_json_fields,
)

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a pharmacovigilance case processor working under ICH E2A.

Extract structured information from an Individual Case Safety Report (ICSR) narrative.
Extract only what the text states. If a field is not mentioned, return null (or an empty list).
Never infer or invent information.

ICH E2A requires four elements for a valid case:
1. An identifiable patient
2. An identifiable reporter
3. A suspect medicinal product
4. An adverse event or reaction

Return ONLY valid JSON with these exact keys:
{
  "patient": "patient identifier or description (e.g., '45-year-old female')",
  "patient_age": "age if stated",
  "patient_sex": "sex if stated",
  "reporter": "reporter name or identifier",
  "reporter_type": "HCP / Consumer / Literature / Regulatory Authority / Company",
  "suspect_product": "drug/product name (generic name if given)",
  "suspect_product_dose": "dose and route if stated",
  "suspect_product_indication": "indication for use if stated",
  "adverse_event": "adverse event / reaction as described in the report",
  "adverse_event_pt": "the single MedDRA preferred term that best fits the PRIMARY event (e.g. 'Haemorrhage intracranial', 'Immune-mediated myocarditis', 'Lactic acidosis'), or null if unsure",
  "adverse_event_onset": "onset date if stated",
  "adverse_event_outcome": "outcome (recovered, recovering, fatal, ongoing, unknown, etc.)",
  "therapy_start_date": "start date of the suspect product if stated",
  "therapy_stop_date": "stop date or date of withdrawal if stated",
  "time_to_onset": "time from first dose (or dose change) to event, only if stated or directly computable from stated dates",
  "dose_exposure": "dose, frequency, route, duration and any recent dose changes, as stated",
  "dechallenge": "Positive / Negative / Not done / Unknown, followed by the supporting detail",
  "rechallenge": "Positive / Negative / Not done / Unknown, followed by the supporting detail",
  "medical_history": ["relevant medical history items"],
  "concomitant_medications": ["concomitant drugs with dose if stated"],
  "relevant_tests": ["lab, imaging or biopsy results with values and dates where stated"],
  "four_element_valid": true or false,
  "missing_elements": ["list of missing ICH E2A elements, empty if all present"]
}"""


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)]


def extract_entities(narrative: str, case_id: str, client: Anthropic) -> CaseEntities:
    """Extract case entities from narrative text using Claude."""
    logger.info(f"Extracting entities for case {case_id}")

    response = create_message(
        client,
        max_tokens=2000,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Extract entities from this case report:\n\n{narrative[:12000]}"
        }]
    )

    data = parse_json_response(response, "entity extraction")
    require_json_fields(
        data,
        {
            "patient", "patient_age", "patient_sex", "reporter", "reporter_type",
            "suspect_product", "suspect_product_dose", "suspect_product_indication",
            "adverse_event", "adverse_event_pt", "adverse_event_onset",
            "adverse_event_outcome", "therapy_start_date", "therapy_stop_date",
            "time_to_onset", "dose_exposure", "dechallenge", "rechallenge",
            "medical_history", "concomitant_medications", "relevant_tests",
            "four_element_valid", "missing_elements",
        },
        "entity extraction",
    )

    return CaseEntities(
        case_id=case_id,
        patient=data.get("patient"),
        patient_age=data.get("patient_age"),
        patient_sex=data.get("patient_sex"),
        reporter=data.get("reporter"),
        reporter_type=data.get("reporter_type"),
        suspect_product=data.get("suspect_product"),
        suspect_product_dose=data.get("suspect_product_dose"),
        suspect_product_indication=data.get("suspect_product_indication"),
        adverse_event=data.get("adverse_event"),
        adverse_event_pt=data.get("adverse_event_pt"),
        adverse_event_onset=data.get("adverse_event_onset"),
        adverse_event_outcome=data.get("adverse_event_outcome"),
        therapy_start_date=data.get("therapy_start_date"),
        therapy_stop_date=data.get("therapy_stop_date"),
        time_to_onset=data.get("time_to_onset"),
        dose_exposure=data.get("dose_exposure"),
        dechallenge=data.get("dechallenge"),
        rechallenge=data.get("rechallenge"),
        medical_history=_as_list(data.get("medical_history")),
        concomitant_medications=_as_list(data.get("concomitant_medications")),
        relevant_tests=_as_list(data.get("relevant_tests")),
        four_element_valid=bool(data.get("four_element_valid", False)),
        missing_elements=_as_list(data.get("missing_elements")),
        source_narrative=narrative
    )
