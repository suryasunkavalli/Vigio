import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.services.anthropic_service import (
    AnthropicConfigurationError,
    AnthropicResponseError,
    get_anthropic_settings,
    parse_json_response,
    require_json_fields,
)


def response_with(text: str):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)]
    )


class AnthropicServiceTests(unittest.TestCase):
    def test_settings_require_key_and_model(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AnthropicConfigurationError):
                get_anthropic_settings()

    def test_parses_json_object(self):
        data = parse_json_response(response_with('{"ok": true}'), "test")
        self.assertTrue(data["ok"])

    def test_parses_json_wrapped_in_explanatory_text(self):
        data = parse_json_response(
            response_with('Here is the result:\n```json\n{"ok": true}\n```'),
            "test",
        )
        self.assertTrue(data["ok"])

    def test_rejects_invalid_json(self):
        with self.assertRaises(AnthropicResponseError):
            parse_json_response(response_with("not JSON"), "test")

    def test_rejects_missing_required_fields(self):
        with self.assertRaises(AnthropicResponseError):
            require_json_fields({}, {"required"}, "test")


if __name__ == "__main__":
    unittest.main()
