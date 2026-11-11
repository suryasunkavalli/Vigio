import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from backend.models.case import CaseEntities
from backend.services.population_intelligence import (
    FAERSQueryResult,
    assess_population_intelligence,
    query_faers_event_count,
)


def api_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=httpx.Request("GET", "https://api.fda.gov/drug/event.json"),
        json=payload,
    )


class PopulationIntelligenceTests(unittest.TestCase):
    @patch("backend.services.population_intelligence.httpx.get")
    def test_successful_count(self, mock_get):
        mock_get.return_value = api_response(
            200, {"meta": {"results": {"total": 42}}}
        )

        result = query_faers_event_count("Drug", "Event")

        self.assertEqual(result.count, 42)
        self.assertEqual(result.status, "success")

    @patch("backend.services.population_intelligence.httpx.get")
    def test_no_matches_is_not_an_api_failure(self, mock_get):
        mock_get.return_value = api_response(
            404, {"error": {"message": "No matches found!"}}
        )

        result = query_faers_event_count("Drug", "Unknown event")

        self.assertEqual(result.count, 0)
        self.assertEqual(result.status, "no_results")

    @patch("backend.services.population_intelligence.httpx.get")
    def test_api_failure_has_no_count(self, mock_get):
        mock_get.return_value = api_response(
            503, {"error": {"message": "Service unavailable"}}
        )

        result = query_faers_event_count("Drug", "Event")

        self.assertIsNone(result.count)
        self.assertEqual(result.status, "unavailable")

    @patch("backend.services.population_intelligence.create_message")
    @patch("backend.services.population_intelligence.query_faers_drug_total")
    @patch("backend.services.population_intelligence.query_faers_event_count")
    def test_openfda_failure_does_not_stop_assessment(
        self, mock_event, mock_drug, mock_message
    ):
        unavailable = FAERSQueryResult(None, "unavailable", "OpenFDA unavailable")
        mock_event.return_value = unavailable
        mock_drug.return_value = unavailable
        mock_message.return_value = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Population context unavailable.\nUse case evidence.")]
        )
        entities = CaseEntities(
            case_id="test-case",
            suspect_product="TestDrug",
            adverse_event="TestEvent",
        )

        result = assess_population_intelligence(entities, SimpleNamespace())

        self.assertEqual(result.faers_signal.query_status, "unavailable")
        self.assertIsNone(result.faers_signal.report_count)
        self.assertIsNone(result.faers_signal.reporting_odds_ratio)


if __name__ == "__main__":
    unittest.main()
