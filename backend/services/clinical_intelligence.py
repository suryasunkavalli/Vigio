"""
Layer 2: Clinical Intelligence
- PubMed/NCBI literature search for mechanistic evidence
- Returns PMID-cited references
- Clinical plausibility assessment
"""

import httpx
import logging
from anthropic import Anthropic
from backend.models.case import CaseEntities, ClinicalIntelligence, PubMedReference
from backend.services.anthropic_service import (
    create_message, parse_json_response, require_json_fields
)

logger = logging.getLogger(__name__)

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def build_pubmed_query(drug: str, event: str) -> str:
    """Build a PubMed query for drug-event mechanistic literature."""
    drug_clean = drug.split()[0] if drug else ""  # Use first word (generic name)
    event_clean = event.replace(" ", "+") if event else ""
    return f'"{drug_clean}"[tiab] AND "{event_clean}"[tiab] AND (case report[pt] OR adverse[tiab] OR toxicity[tiab])'


def search_pubmed(query: str, max_results: int = 5) -> list[str]:
    """Search PubMed and return list of PMIDs."""
    try:
        resp = httpx.get(
            f"{PUBMED_BASE}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
                "sort": "relevance"
            },
            timeout=10.0
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        logger.warning(f"PubMed search failed: {e}")
        return []


def fetch_pubmed_summaries(pmids: list[str]) -> list[dict]:
    """Fetch article summaries for a list of PMIDs."""
    if not pmids:
        return []
    try:
        resp = httpx.get(
            f"{PUBMED_BASE}/esummary.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "json"
            },
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
                    author_str += f" et al."
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


CLINICAL_SYNTHESIS_PROMPT = """You are a clinical pharmacologist and pharmacovigilance medical reviewer.

Given a drug-adverse event pair and a set of PubMed article titles/metadata, provide:
1. A mechanistic summary explaining the biological plausibility of this drug causing this adverse event
2. A relevance summary for each article (1-2 sentences)
3. A clinical plausibility rating: High / Moderate / Low / Unknown
4. A label cross-reference note (whether this type of event is known for this drug class)

Be precise. Cite only what is supportable. If the mechanism is unknown, say so.

Return ONLY valid JSON:
{
  "mechanistic_summary": "paragraph explaining mechanism",
  "clinical_plausibility": "High" | "Moderate" | "Low" | "Unknown",
  "clinical_notes": "additional clinical context",
  "label_cross_reference": "note about class labeling / known drug effects",
  "article_relevance": {
    "<pmid>": "1-2 sentence relevance summary"
  }
}"""


def assess_clinical_intelligence(
    entities: CaseEntities,
    client: Anthropic
) -> ClinicalIntelligence:
    """
    Run clinical intelligence layer:
    1. Search PubMed for mechanistic literature
    2. Use Claude to synthesize mechanistic explanation with PMID citations
    """
    logger.info(f"Running clinical intelligence for case {entities.case_id}")

    drug = entities.suspect_product or ""
    event = entities.adverse_event or ""

    # Search PubMed
    query = build_pubmed_query(drug, event)
    pmids = search_pubmed(query, max_results=5)
    articles = fetch_pubmed_summaries(pmids)

    logger.info(f"Found {len(articles)} PubMed articles for '{drug}' + '{event}'")

    # Build context for Claude
    articles_text = ""
    if articles:
        for a in articles:
            articles_text += f"PMID {a['pmid']}: {a['title']} — {a['authors']} ({a['journal']}, {a['year']})\n"
    else:
        articles_text = "No PubMed articles found for this drug-event combination."

    prompt = f"""Drug: {drug}
Adverse Event: {event}
Patient Context: {entities.patient_age or 'unknown age'}, {entities.patient_sex or 'unknown sex'}
Indication: {entities.suspect_product_indication or 'not stated'}
Outcome: {entities.adverse_event_outcome or 'not stated'}

PubMed Search Results:
{articles_text}

Provide clinical intelligence assessment."""

    response = create_message(
        client,
        max_tokens=1500,
        system=CLINICAL_SYNTHESIS_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    data = parse_json_response(response, "clinical intelligence")
    require_json_fields(
        data,
        {
            "mechanistic_summary", "clinical_plausibility", "clinical_notes",
            "label_cross_reference", "article_relevance",
        },
        "clinical intelligence",
    )

    article_relevance = data.get("article_relevance", {})

    references = [
        PubMedReference(
            pmid=a["pmid"],
            title=a["title"],
            authors=a["authors"],
            journal=a["journal"],
            year=a["year"],
            relevance_summary=article_relevance.get(a["pmid"], "Relevant to drug-event pair"),
            url=a["url"]
        )
        for a in articles
    ]

    return ClinicalIntelligence(
        mechanistic_summary=data.get("mechanistic_summary", "Mechanism not established in available literature."),
        pubmed_references=references,
        label_cross_reference=data.get("label_cross_reference", ""),
        clinical_plausibility=data.get("clinical_plausibility", "Unknown"),
        clinical_notes=data.get("clinical_notes", "")
    )
