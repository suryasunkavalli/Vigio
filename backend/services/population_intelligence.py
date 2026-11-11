"""Layer 3: OpenFDA FAERS report-count context for a case."""

import logging
from dataclasses import dataclass
from typing import Literal

import httpx
from anthropic import Anthropic

from backend.models.case import CaseEntities, FAERSSignal, PopulationIntelligence
from backend.services.anthropic_service import create_message, response_text

logger = logging.getLogger(__name__)

OPENFDA_BASE = "https://api.fda.gov/drug/event.json"
QueryStatus = Literal["success", "no_results", "unavailable"]


@dataclass(frozen=True)
class FAERSQueryResult:
    count: int | None
    status: QueryStatus
    note: str


def _query_faers_count(search: str, description: str) -> FAERSQueryResult:
    """Query one OpenFDA count while preserving no-result and failure states."""
    try:
        response = httpx.get(
            OPENFDA_BASE,
            params={"search": search, "limit": 1},
            timeout=10.0,
        )

        if response.status_code == 200:
            total = response.json().get("meta", {}).get("results", {}).get("total")
            if not isinstance(total, int):
                return FAERSQueryResult(
                    count=None,
                    status="unavailable",
                    note=f"OpenFDA returned no usable total for {description}.",
                )
            return FAERSQueryResult(
                count=total,
                status="success",
                note=f"OpenFDA returned a report count for {description}.",
            )

        if response.status_code == 404:
            try:
                error_message = response.json().get("error", {}).get("message", "")
            except ValueError:
                error_message = ""
            if "no matches" in error_message.lower():
                return FAERSQueryResult(
                    count=0,
                    status="no_results",
                    note=f"OpenFDA found no matching reports for {description}.",
                )

        response.raise_for_status()
        return FAERSQueryResult(
            count=None,
            status="unavailable",
            note=f"OpenFDA did not return a usable result for {description}.",
        )
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.warning("FAERS query unavailable for %s: %s", description, exc)
        return FAERSQueryResult(
            count=None,
            status="unavailable",
            note=f"OpenFDA was unavailable for {description}.",
        )


def query_faers_event_count(drug: str, event: str) -> FAERSQueryResult:
    return _query_faers_count(
        f'patient.drug.medicinalproduct:"{drug}" AND patient.reaction.reactionmeddrapt:"{event}"',
        f"{drug} and {event}",
    )


def query_faers_drug_total(drug: str) -> FAERSQueryResult:
    return _query_faers_count(
        f'patient.drug.medicinalproduct:"{drug}"',
        drug,
    )


def _display_count(result: FAERSQueryResult) -> str:
    return f"{result.count:,}" if result.count is not None else "unavailable"


def _combined_status(
    event_result: FAERSQueryResult,
    drug_result: FAERSQueryResult,
) -> tuple[str, str]:
    if event_result.status == "unavailable" and drug_result.status == "unavailable":
        return "unavailable", "OpenFDA queries were unavailable."
    if event_result.status == "unavailable" or drug_result.status == "unavailable":
        return "partial", "One OpenFDA query was unavailable; available counts are shown."
    if event_result.status == "no_results":
        return "no_results", "OpenFDA found no matching drug-event reports."
    return "success", "OpenFDA report counts were retrieved successfully."


def assess_population_intelligence(
    entities: CaseEntities,
    client: Anthropic,
) -> PopulationIntelligence:
    """Retrieve FAERS counts and synthesize cautious population context."""
    logger.info("Running population intelligence for case %s", entities.case_id)

    drug = (entities.suspect_product or "").split()[0]
    event = entities.adverse_event or ""

    if not drug or not event:
        return PopulationIntelligence(
            signal_summary="Insufficient case data to query OpenFDA FAERS.",
            population_notes="Drug name or adverse event term was not identified.",
        )

    event_result = query_faers_event_count(drug, event)
    drug_result = query_faers_drug_total(drug)
    query_status, query_note = _combined_status(event_result, drug_result)

    faers_signal = FAERSSignal(
        drug_name=drug,
        event_term=event,
        report_count=event_result.count,
        total_drug_reports=drug_result.count,
        reporting_odds_ratio=None,
        signal_strength="Not calculated (MVP)",
        query_status=query_status,
        query_note=query_note,
    )

    prompt = f"""Drug: {drug}
Adverse Event: {event}

OpenFDA FAERS query results:
- Drug-event reports: {_display_count(event_result)}
- Total reports for the drug: {_display_count(drug_result)}
- Query status: {query_status}
- Query note: {query_note}
- Reporting Odds Ratio: not calculated in this MVP

Provide:
1. A cautious population-context summary for a regulatory reviewer
2. Relevant limitations of spontaneous-report data

Do not infer missing report counts or a signal strength. Do not claim causality.
State clearly that a report count is not an incidence rate and that ROR was not calculated."""

    response = create_message(
        client,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    synthesis = response_text(response, "population intelligence")
    lines = synthesis.split("\n")

    return PopulationIntelligence(
        faers_signal=faers_signal,
        background_context=(
            f"OpenFDA FAERS drug-event reports: {_display_count(event_result)}. "
            f"Total drug reports: {_display_count(drug_result)}. ROR unavailable in MVP."
        ),
        population_notes="\n".join(lines[1:]).strip() if len(lines) > 1 else "",
        signal_summary=lines[0] if lines else synthesis,
    )
