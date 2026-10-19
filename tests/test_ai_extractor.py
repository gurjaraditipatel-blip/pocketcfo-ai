import json
import unittest
from io import BytesIO
from unittest.mock import patch

from pocketcfo.ai_extractor import (
    InvoiceExtractionError,
    extract_invoice_fields,
)


class OllamaExtractorTests(unittest.TestCase):
    def test_calls_configured_local_model_and_parses_json(self) -> None:
        model_result = {
            "fields": {
                "vendor": "Example Studio",
                "invoice_number": "INV-17",
                "issue_date": "2025-04-02",
                "due_date": None,
                "currency": "USD",
                "total_amount": "300.00",
                "tax_amount": None,
            },
            "confidence": {
                "vendor": 0.95,
                "invoice_number": 0.96,
                "issue_date": 0.92,
                "due_date": 0.0,
                "currency": 0.94,
                "total_amount": 0.98,
                "tax_amount": 0.0,
            },
        }
        api_result = {
            "message": {"content": json.dumps(model_result)},
        }
        response = BytesIO(json.dumps(api_result).encode("utf-8"))
        response.__enter__ = lambda: response
        response.__exit__ = lambda *args: None

        with patch("pocketcfo.ai_extractor.urlopen", return_value=response) as mocked:
            result = extract_invoice_fields("Synthetic invoice total: USD 300.00")

        request = mocked.call_args.args[0]
        request_body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request_body["model"], "qwen2.5:3b")
        self.assertEqual(request_body["stream"], False)
        self.assertEqual(result["fields"]["vendor"], "Example Studio")
        self.assertIn("due_date", result["review_fields"])

    def test_does_not_call_ollama_for_empty_text(self) -> None:
        with patch("pocketcfo.ai_extractor.urlopen") as mocked:
            with self.assertRaises(InvoiceExtractionError):
                extract_invoice_fields("   ")
        mocked.assert_not_called()

    def test_rejects_oversized_text_instead_of_silently_truncating(self) -> None:
        with patch("pocketcfo.ai_extractor.urlopen") as mocked:
            with self.assertRaisesRegex(InvoiceExtractionError, "40,000 characters"):
                extract_invoice_fields("x" * 40_001)
        mocked.assert_not_called()

    def test_reports_unreachable_local_service(self) -> None:
        from urllib.error import URLError

        with patch(
            "pocketcfo.ai_extractor.urlopen",
            side_effect=URLError("connection refused"),
        ):
            with self.assertRaisesRegex(InvoiceExtractionError, "Could not reach"):
                extract_invoice_fields("Synthetic invoice")

    def test_reports_invalid_model_json(self) -> None:
        response_body = {"message": {"content": "not json"}}
        response = BytesIO(json.dumps(response_body).encode("utf-8"))
        response.__enter__ = lambda: response
        response.__exit__ = lambda *args: None

        with patch("pocketcfo.ai_extractor.urlopen", return_value=response):
            with self.assertRaisesRegex(InvoiceExtractionError, "valid invoice JSON"):
                extract_invoice_fields("Synthetic invoice")


if __name__ == "__main__":
    unittest.main()
