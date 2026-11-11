"""
Lens 3: Population Safety & Evidence Generation
Question: what do many cases and other data tell us about risk across a population?

MVP scope:
- FAERS disproportionality for the drug-event pair (ROR with 95% CI). Source order:
  1. local deduplicated snapshot built from FDA quarterly files (tools/build_faers_db.py)
  2. live openFDA counts as a fallback
- Descriptive subgroup breakdown (sex, age group) of the FAERS reports
- Evidence-gap identification: what this case, the literature and FAERS cannot answer,
  and what data (claims, EHR, registry, study) would answer it

Roadmap (not in MVP): aggregate analysis of a customer's own ICSRs, signal evaluation
workflow, observed-vs-expected analysis, epidemiology and real-world evidence studies.
"""

import logging
import httpx
from anthropic import Anthropic
from backend.services.disproportionality import calculate_ror, classify_signal, data_confidence  # noqa: F401
from backend.services import faers_local
from backend.services.anthropic_service import (
    create_message,
    parse_json_response,
    require_json_fields,
)
from backend.models.case import (
    CaseEntities, ClinicalIntelligence, PopulationIntelligence,
    FAERSSignal, SubgroupBreakdown, EvidenceGap
)

logger = logging.getLogger(__name__)

OPENFDA_BASE = "https://api.fda.gov/drug/event.json"

SEX_CODES = {"0": "Unknown", "1": "Male", "2": "Female"}
AGE_GROUP_CODES = {"1": "Neonate", "2": "Infant", "3": "Child", "4": "Adolescent", "5": "Adult", "6": "Elderly"}


def _drug_clause(drug: str) -> str:
    return f'(patient.drug.openfda.generic_name:"{drug}" OR patient.drug.medicinalproduct:"{drug}")'


def _event_clause(event: str) -> str:
    return f'patient.reaction.reactionmeddrapt:"{event}"'


def openfda_total(search: str | None) -> int:
    """Number of FAERS reports matching a search (or the whole database when search is None)."""
    params = {"limit": 1}
    if search:
        params["search"] = search
    try:
        resp = httpx.get(OPENFDA_BASE, params=params, timeout=15.0)
        if resp.status_code == 404:  # openFDA returns 404 when nothing matches
            return 0
        resp.raise_for_status()
        return int(resp.json().get("meta", {}).get("results", {}).get("total", 0))
    except Exception as e:
        logger.warning(f"openFDA count failed for search={search!r}: {e}")
        return -1  # unknown, distinct from zero


def openfda_count_by(search: str, field: str, labels: dict) -> dict:
    """Count matching reports grouped by a coded field."""
    try:
        resp = httpx.get(OPENFDA_BASE, params={"search": search, "count": field}, timeout=15.0)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return {labels.get(str(r["term"]), str(r["term"])): int(r["count"]) for r in resp.json().get("results", [])}
    except Exception as e:
        logger.warning(f"openFDA breakdown by {field} failed: {e}")
        return {}


POPULATION_SYSTEM_PROMPT = """You are a pharmacoepidemiologist supporting a drug safety reviewer.

Using ONLY the FAERS figures and case context provided:
1. Write a 2-3 sentence population signal summary. Do not overstate it: FAERS is voluntary,
   subject to under-reporting and stimulated reporting, has no denominator of exposed patients,
   and disproportionality does not establish causality or incidence.
2. Give background context and caveats specific to this drug-event pair.
3. Identify 2-4 evidence gaps: questions that this case, the literature and FAERS cannot answer,
   why each matters for benefit-risk, and what data would answer it
   (e.g. claims database, EHR cohort, disease registry, observed-vs-expected analysis, targeted study).

Do not invent numbers. Return ONLY valid JSON:
{
  "signal_summary": "...",
  "background_context": "...",
  "population_notes": "...",
  "evidence_gaps": [
    {"question": "...", "why_it_matters": "...", "data_that_would_answer": "..."}
  ]
}"""


def _summary_text(faers: FAERSSignal, subgroups, extra: str = "") -> str:
    ror, lo = faers.reporting_odds_ratio, faers.ror_ci_lower
    return (
        f"Source: {faers.data_source}\n"
        f"Reports with {faers.drug_name} (suspect) and {faers.event_term}: {faers.report_count:,}\n"
        f"All reports with {faers.drug_name} as suspect: {faers.total_drug_reports:,}\n"
        f"All reports with {faers.event_term}: {faers.event_total_reports:,}\n"
        f"All reports in database: {faers.database_total_reports:,}\n"
        f"ROR: {ror if ror is not None else 'not calculable'}"
        + (f" (95% CI {lo}-{faers.ror_ci_upper})" if lo is not None else "")
        + f"\nClassification: {faers.signal_strength}; data confidence: {faers.data_confidence}"
        + (f"\nBy sex: {subgroups.by_sex}\nBy age group: {subgroups.by_age_group}" if subgroups else "")
        + (f"\nOutcomes: {subgroups.outcomes}" if subgroups and subgroups.outcomes else "")
        + extra
    )


def _from_local(r: dict, drug: str, event: str):
    """Build the signal from the local deduplicated FAERS snapshot."""
    if not r["pt"]:
        faers = FAERSSignal(
            drug_name=r["ingredient"], event_term=event, report_count=0, total_drug_reports=r["drug_total"],
            database_total_reports=r["n_total"], signal_strength="Event term not matched to a MedDRA PT",
            data_confidence="Low", data_source=r["source"], data_period=r["data_period"],
            match_notes=f"Drug: {r['drug_match']}. Event: {r['event_match']}."
        )
        return faers, None, _summary_text(faers, None, "\nEvent term could not be matched; no disproportionality computed.")
    ror, lo, hi = calculate_ror(r["a"], r["drug_total"], r["event_total"], r["n_total"])
    is_sdr, strength = classify_signal(r["a"], ror, lo)
    faers = FAERSSignal(
        drug_name=r["ingredient"], event_term=r["pt"], report_count=r["a"], total_drug_reports=r["drug_total"],
        event_total_reports=r["event_total"], database_total_reports=r["n_total"],
        reporting_odds_ratio=ror, ror_ci_lower=lo, ror_ci_upper=hi, is_sdr=is_sdr,
        signal_strength=strength, data_confidence=data_confidence(r["a"]),
        data_source=r["source"], data_period=r["data_period"],
        match_notes=f"Drug: {r['drug_match']}. Event: {r['event_match']}."
        + (f" Other candidate PTs: {', '.join(r['alternative_pts'])}." if r["alternative_pts"] else "")
    )
    subgroups = SubgroupBreakdown(by_sex=r["by_sex"], by_age_group=r["by_age_group"], outcomes=r["outcomes"]) if r["a"] else None
    return faers, subgroups, _summary_text(faers, subgroups)


def _from_openfda(drug: str, event: str):
    """Fallback: live openFDA counts (not deduplicated, any drug role)."""
    drug_q, event_q = _drug_clause(drug), _event_clause(event)
    a = openfda_total(f"{drug_q} AND {event_q}")
    drug_total = openfda_total(drug_q)
    event_total = openfda_total(event_q)
    n_total = openfda_total(None)
    if min(a, drug_total, event_total, n_total) < 0:
        return None, None, "FAERS query failed; no disproportionality figures available."
    ror, lo, hi = calculate_ror(a, drug_total, event_total, n_total)
    is_sdr, strength = classify_signal(a, ror, lo)
    faers = FAERSSignal(
        drug_name=drug, event_term=event, report_count=a, total_drug_reports=drug_total,
        event_total_reports=event_total, database_total_reports=n_total,
        reporting_odds_ratio=ror, ror_ci_lower=lo, ror_ci_upper=hi,
        is_sdr=is_sdr, signal_strength=strength, data_confidence=data_confidence(a),
        data_source="FDA FAERS via openFDA (live; not deduplicated, any drug role)"
    )
    pair_q = f"{drug_q} AND {event_q}"
    subgroups = SubgroupBreakdown(
        by_sex=openfda_count_by(pair_q, "patient.patientsex", SEX_CODES),
        by_age_group=openfda_count_by(pair_q, "patient.patientagegroup", AGE_GROUP_CODES)
    ) if a > 0 else None
    return faers, subgroups, _summary_text(faers, subgroups)


def assess_population_intelligence(
    entities: CaseEntities,
    client: Anthropic,
    clinical: ClinicalIntelligence | None = None
) -> PopulationIntelligence:
    """Run the Population Safety & Evidence Generation lens."""
    logger.info(f"Running Population Safety lens for case {entities.case_id}")

    drug = (entities.suspect_product or "").split()[0] if entities.suspect_product else ""
    event = entities.adverse_event_pt or entities.adverse_event or ""
    if not drug or not event:
        return PopulationIntelligence(
            signal_summary="Insufficient case data to query FAERS.",
            population_notes="Drug name or adverse event term not identified in the case."
        )

    local = faers_local.lookup(entities.suspect_product or drug, event, entities.adverse_event_pt)
    if local is not None:
        faers, subgroups, faers_text = _from_local(local, drug, event)
    else:
        faers, subgroups, faers_text = _from_openfda(drug, event)

    clinical_text = ""
    if clinical:
        clinical_text = (
            f"\nClinical lens: {clinical.case_clinical_summary}\n"
            f"Risk factors: {', '.join(clinical.risk_factors)}\n"
            f"Proposed causality: {clinical.causality.category.value}"
        )

    response = create_message(
        client,
        max_tokens=3000,
        system=POPULATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Drug: {drug}\nEvent: {event}\n\nFAERS:\n{faers_text}\n{clinical_text}"}]
    )
    data = parse_json_response(response, "population lens")
    require_json_fields(
        data,
        {"signal_summary", "background_context", "population_notes", "evidence_gaps"},
        "population lens",
    )

    gaps = [
        EvidenceGap(
            question=g.get("question", ""),
            why_it_matters=g.get("why_it_matters", ""),
            data_that_would_answer=g.get("data_that_would_answer", "")
        )
        for g in (data.get("evidence_gaps") or []) if isinstance(g, dict) and g.get("question")
    ]

    return PopulationIntelligence(
        faers_signal=faers,
        subgroups=subgroups,
        signal_summary=data.get("signal_summary", faers_text.splitlines()[0]),
        background_context=data.get("background_context", ""),
        population_notes=data.get("population_notes", ""),
        evidence_gaps=gaps
    )
