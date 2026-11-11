"""
Entity extraction service.
Uses Claude to extract the ICH E2A four elements and supporting case data
from the raw case narrative text.
"""

import logging
from anthropic import Anthropic
from backend.models.case import CaseEntities
from backend.services.anthropic_service import (
    create_message, parse_json_response, require_json_fields
)

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a pharmacovigilance expert specializing in case processing under ICH E2A guidelines.

Your task is to extract structured information from an Individual Case Safety Report (ICSR) narrative.

Extract the following fields precisely as they appear in the text. If a field is not mentioned, return null.
Do not infer or hallucinate information not present in the text.

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
  "suspect_product": "drug/product name",
  "suspect_product_dose": "dose and route if stated",
  "suspect_product_indication": "indication for use if stated",
  "adverse_event": "adverse event / reaction term",
  "adverse_event_onset": "onset date or time to onset if stated",
  "adverse_event_outcome": "outcome (recovered, fatal, ongoing, unknown, etc.)",
  "four_element_valid": true or false,
  "missing_elements": ["list of missing ICH E2A elements, empty if all present"]
}"""


def extract_entities(narrative: str, case_id: str, client: Anthropic) -> CaseEntities:
    """
    Extract case entities from narrative text using Claude.
    Returns a CaseEntities object with all four ICH E2A elements assessed.
    """
    logger.info(f"Extracting entities for case {case_id}")

    response = create_message(
        client,
        max_tokens=1024,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Extract entities from this case report:\n\n{narrative[:8000]}"
            }
        ]
    )

    data = parse_json_response(response, "entity extraction")
    require_json_fields(
        data,
        {
            "patient", "patient_age", "patient_sex", "reporter", "reporter_type",
            "suspect_product", "suspect_product_dose", "suspect_product_indication",
            "adverse_event", "adverse_event_onset", "adverse_event_outcome",
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
        adverse_event_onset=data.get("adverse_event_onset"),
        adverse_event_outcome=data.get("adverse_event_outcome"),
        four_element_valid=data.get("four_element_valid", False),
        missing_elements=data.get("missing_elements", []),
        source_narrative=narrative
    )
