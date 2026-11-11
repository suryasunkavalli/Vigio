"""
Lens 2: Clinical Safety
Question: what does the case tell us medically about the patient's experience and
the product's safety profile?

- Case-level medical review: timing, exposure, dechallenge/rechallenge
- Risk factors and alternative causes (history, concomitant medications)
- WHO-UMC causality proposal with reasoning (the reviewer confirms or changes it)
- Follow-up questions for missing information
- Literature evidence from PubMed (real PMIDs only) and mechanism
"""

import httpx
import logging
from anthropic import Anthropic
from backend.models.case import (
    CaseEntities, ClinicalIntelligence, PubMedReference,
    CausalityAssessment, CausalityCategory
)
from backend.services.anthropic_service import (
    create_message,
    parse_json_response,
    require_json_fields,
)

logger = logging.getLogger(__name__)

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def build_pubmed_query(drug: str, event: str) -> str:
    """Build a PubMed query for drug-event literature."""
    drug_clean = drug.split()[0] if drug else ""
    return f'"{drug_clean}"[tiab] AND "{event}"[tiab]'


def search_pubmed(query: str, max_results: int = 5) -> list[str]:
    """Search PubMed and return a list of PMIDs."""
    try:
        resp = httpx.get(
            f"{PUBMED_BASE}/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmax": max_results,
                    "retmode": "json", "sort": "relevance"},
            timeout=10.0
        )
        resp.raise_for_status()
        return resp.json().get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        logger.warning(f"PubMed search failed: {e}")
        return []


def fetch_pubmed_summaries(pmids: list[str]) -> list[dict]:
    """Fetch article metadata for a list of PMIDs."""
    if not pmids:
        return []
    try:
        resp = httpx.get(
            f"{PUBMED_BASE}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(pmids), "retmode": "json"},
            timeout=10.0
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for pmid in pmids:
            article = data.get("result", {}).get(pmid, {})
            if article and "title" in article:
                authors = article.get("authors", [])
                author_str = authors[0].get("name", "") if authors else "Unknown"
                if len(authors) > 1:
                    author_str += " et al."
                results.append({
                    "pmid": pmid,
                    "title": article.get("title", ""),
                    "authors": author_str,
                    "journal": article.get("source", ""),
                    "year": article.get("pubdate", "")[:4],
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                })
        return results
    except Exception as e:
        logger.warning(f"PubMed summary fetch failed: {e}")
        return []


CLINICAL_SYSTEM_PROMPT = """You are a pharmacovigilance medical reviewer performing a case-level clinical assessment.

Using ONLY the case narrative, the extracted case details and the PubMed metadata provided:

1. Summarize what happened to the patient clinically (3-4 sentences).
2. Assess time-to-onset, dose/exposure, and dechallenge/rechallenge as evidence for or against a causal link.
3. List patient risk factors and plausible alternative causes (disease, concomitant drugs, procedures).
4. Propose a WHO-UMC causality category with reasoning against each criterion:
   Certain | Probable / Likely | Possible | Unlikely | Conditional / Unclassified | Unassessable / Unclassifiable
   This is a proposal for a qualified reviewer to confirm, not a determination.
5. List follow-up questions for the reporter whose answers would change the assessment.
6. Give a short mechanism summary and a clinical plausibility rating.
7. For each PMID provided, a 1-sentence relevance note based on its title. Never cite a PMID that was not provided.

If information is missing, say so rather than assume it.

Return ONLY valid JSON:
{
  "case_clinical_summary": "...",
  "time_to_onset_assessment": "...",
  "dose_exposure_assessment": "...",
  "dechallenge_rechallenge_assessment": "...",
  "risk_factors": ["..."],
  "alternative_causes": ["..."],
  "causality": {
    "category": "one WHO-UMC category from the list above",
    "rationale": "2-3 sentences",
    "criteria": {
      "temporal_relationship": "...",
      "alternative_explanations": "...",
      "dechallenge": "...",
      "rechallenge": "...",
      "known_response_pattern": "..."
    }
  },
  "follow_up_questions": ["..."],
  "mechanistic_summary": "...",
  "clinical_plausibility": "High" | "Moderate" | "Low" | "Unknown",
  "label_cross_reference": "class or label knowledge, clearly marked as general knowledge, not a listedness determination",
  "clinical_notes": "...",
  "article_relevance": {"<pmid>": "..."}
}"""


def _causality_category(value: str | None) -> CausalityCategory:
    for member in CausalityCategory:
        if value and (member.value.lower() == value.lower() or member.value.split(" /")[0].lower() == value.lower()):
            return member
    return CausalityCategory.UNASSESSABLE


def assess_clinical_intelligence(
    entities: CaseEntities,
    narrative: str,
    client: Anthropic
) -> ClinicalIntelligence:
    """Run the Clinical Safety lens."""
    logger.info(f"Running Clinical Safety lens for case {entities.case_id}")

    drug = entities.suspect_product or ""
    event = entities.adverse_event_pt or entities.adverse_event or ""

    articles = fetch_pubmed_summaries(search_pubmed(build_pubmed_query(drug, event))) if drug and event else []
    logger.info(f"Found {len(articles)} PubMed articles for '{drug}' + '{event}'")

    articles_text = "\n".join(
        f"PMID {a['pmid']}: {a['title']} - {a['authors']} ({a['journal']}, {a['year']})" for a in articles
    ) or "No PubMed articles retrieved."

    prompt = f"""CASE NARRATIVE:
{narrative[:8000]}

EXTRACTED DETAILS:
- Patient: {entities.patient_age or 'age unknown'}, {entities.patient_sex or 'sex unknown'}
- Suspect product: {drug}; dose/exposure: {entities.dose_exposure or entities.suspect_product_dose or 'not stated'}
- Indication: {entities.suspect_product_indication or 'not stated'}
- Event: {event}; onset: {entities.adverse_event_onset or 'not stated'}; time to onset: {entities.time_to_onset or 'not stated'}
- Therapy start/stop: {entities.therapy_start_date or '?'} / {entities.therapy_stop_date or '?'}
- Dechallenge: {entities.dechallenge or 'not stated'}; rechallenge: {entities.rechallenge or 'not stated'}
- Medical history: {', '.join(entities.medical_history) or 'not stated'}
- Concomitant medications: {', '.join(entities.concomitant_medications) or 'not stated'}
- Tests: {'; '.join(entities.relevant_tests) or 'not stated'}
- Outcome: {entities.adverse_event_outcome or 'not stated'}

PUBMED RESULTS:
{articles_text}"""

    response = create_message(
        client,
        max_tokens=3000,
        system=CLINICAL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    data = parse_json_response(response, "clinical lens")
    require_json_fields(
        data,
        {
            "case_clinical_summary", "time_to_onset_assessment",
            "dose_exposure_assessment", "dechallenge_rechallenge_assessment",
            "risk_factors", "alternative_causes", "causality",
            "follow_up_questions", "mechanistic_summary", "clinical_plausibility",
            "label_cross_reference", "clinical_notes", "article_relevance",
        },
        "clinical lens",
    )
    relevance = data.get("article_relevance", {}) or {}
    causality = data.get("causality", {}) or {}

    references = [
        PubMedReference(
            pmid=a["pmid"], title=a["title"], authors=a["authors"], journal=a["journal"],
            year=a["year"], url=a["url"],
            relevance_summary=relevance.get(a["pmid"], "Retrieved for this drug-event pair.")
        )
        for a in articles
    ]

    return ClinicalIntelligence(
        case_clinical_summary=data.get("case_clinical_summary", ""),
        time_to_onset_assessment=data.get("time_to_onset_assessment", ""),
        dose_exposure_assessment=data.get("dose_exposure_assessment", ""),
        dechallenge_rechallenge_assessment=data.get("dechallenge_rechallenge_assessment", ""),
        risk_factors=data.get("risk_factors", []) or [],
        alternative_causes=data.get("alternative_causes", []) or [],
        causality=CausalityAssessment(
            category=_causality_category(causality.get("category")),
            rationale=causality.get("rationale", ""),
            criteria={k: str(v) for k, v in (causality.get("criteria") or {}).items()}
        ),
        follow_up_questions=data.get("follow_up_questions", []) or [],
        mechanistic_summary=data.get("mechanistic_summary", "Mechanism not established in the available information."),
        pubmed_references=references,
        label_cross_reference=data.get("label_cross_reference", ""),
        clinical_plausibility=data.get("clinical_plausibility", "Unknown"),
        clinical_notes=data.get("clinical_notes", "")
    )
