import unittest
from unittest.mock import patch

import httpx

from backend.services.disproportionality import calculate_ror, classify_signal, data_confidence
from backend.services.population_intelligence import openfda_total


def api_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=httpx.Request("GET", "https://api.fda.gov/drug/event.json"),
        json=payload,
    )


class PopulationIntelligenceTests(unittest.TestCase):
    def test_ror_and_signal_use_complete_two_by_two_table(self):
        ror, lower, upper = calculate_ror(40, 1_000, 2_000, 100_000)
        self.assertEqual((ror, lower, upper), (2.06, 1.5, 2.84))
        self.assertEqual(classify_signal(40, ror, lower)[0], True)

    def test_empty_cell_cannot_produce_ror(self):
        self.assertEqual(calculate_ror(10, 10, 100, 1_000), (None, None, None))

    def test_confidence_is_based_on_pair_report_volume(self):
        self.assertEqual(data_confidence(5), "Low")
        self.assertEqual(data_confidence(20), "Moderate")
        self.assertEqual(data_confidence(100), "High")

    @patch("backend.services.population_intelligence.httpx.get")
    def test_openfda_count_success(self, mock_get):
        mock_get.return_value = api_response(200, {"meta": {"results": {"total": 42}}})
        self.assertEqual(openfda_total("drug AND event"), 42)

    @patch("backend.services.population_intelligence.httpx.get")
    def test_openfda_no_matches_is_zero(self, mock_get):
        mock_get.return_value = api_response(404, {"error": {"message": "No matches"}})
        self.assertEqual(openfda_total("unknown"), 0)

    @patch("backend.services.population_intelligence.httpx.get")
    def test_openfda_failure_is_unknown_not_zero(self, mock_get):
        mock_get.return_value = api_response(503, {"error": {"message": "Unavailable"}})
        self.assertEqual(openfda_total("drug AND event"), -1)


if __name__ == "__main__":
    unittest.main()
