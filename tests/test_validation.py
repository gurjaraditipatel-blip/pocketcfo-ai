import unittest
from decimal import Decimal

from pocketcfo.validation import (
    InputValidationError,
    parse_amount,
    parse_iso_date,
    prepare_extracted_invoice,
    invoice_transaction_defaults,
    validate_invoice_input,
    validate_transaction_input,
)


class InvoiceAndTransactionValidationTests(unittest.TestCase):
    def test_parses_comma_separated_amount(self) -> None:
        self.assertEqual(parse_amount("1,234.50", required=True), Decimal("1234.50"))

    def test_rejects_negative_or_over_precise_amounts(self) -> None:
        for value in ("-1.00", "1.234", "NaN", "1,23.00"):
            with self.subTest(value=value):
                with self.assertRaises(InputValidationError):
                    parse_amount(value)

    def test_rejects_unreasonably_long_amount_input(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "too long"):
            parse_amount("9" * 65)

    def test_rejects_amounts_that_exceed_decimal_precision(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "too large"):
            parse_amount("9" * 40)

    def test_validates_real_iso_calendar_dates(self) -> None:
        self.assertEqual(
            parse_iso_date("2025-02-28", field_name="issue date"),
            "2025-02-28",
        )
        with self.assertRaisesRegex(InputValidationError, "calendar date"):
            parse_iso_date("2025-02-30", field_name="issue date")

    def test_requires_confirmed_invoice_fields_without_guessing(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "vendor"):
            validate_invoice_input(
                {
                    "vendor": "",
                    "currency": "",
                    "total_amount": "",
                }
            )

    def test_normalizes_invoice_values(self) -> None:
        invoice = validate_invoice_input(
            {
                "vendor": "  Example Studio ",
                "invoice_number": " INV-001 ",
                "issue_date": "2025-01-02",
                "currency": "usd",
                "total_amount": "125.50",
                "tax_amount": "",
            }
        )
        self.assertEqual(invoice["vendor"], "Example Studio")
        self.assertEqual(invoice["currency"], "USD")
        self.assertEqual(invoice["total_amount"], Decimal("125.50"))
        self.assertIsNone(invoice["due_date"])
        self.assertIsNone(invoice["tax_amount"])

    def test_transaction_requires_positive_amount_and_date(self) -> None:
        values = {
            "kind": "expense",
            "transaction_date": "2025-01-02",
            "description": "Software subscription",
            "amount": "0",
            "currency": "USD",
        }
        with self.assertRaisesRegex(InputValidationError, "greater than zero"):
            validate_transaction_input(values)

        values["amount"] = "20"
        values["transaction_date"] = ""
        with self.assertRaisesRegex(InputValidationError, "transaction date"):
            validate_transaction_input(values)

    def test_invoice_transaction_draft_requires_explicit_type_and_prefills_fields(self) -> None:
        invoice = {
            "id": 7,
            "vendor": "Example Studio",
            "issue_date": "2025-01-02",
            "currency": "USD",
            "total_amount": "125.00",
        }
        with self.assertRaisesRegex(InputValidationError, "Choose income or expense"):
            invoice_transaction_defaults(invoice, None)

        draft = invoice_transaction_defaults(invoice, "expense")
        self.assertEqual(
            draft,
            {
                "kind": "expense",
                "transaction_date": "2025-01-02",
                "description": "Example Studio",
                "category": "",
                "amount": "125.00",
                "currency": "USD",
                "invoice_id": 7,
            },
        )

    def test_invoice_without_issue_date_does_not_guess_transaction_date(self) -> None:
        draft = invoice_transaction_defaults(
            {
                "id": 8,
                "vendor": "Example Studio",
                "issue_date": None,
                "currency": "EUR",
                "total_amount": "80.00",
            },
            "income",
        )
        self.assertEqual(draft["transaction_date"], "")

    def test_missing_and_low_confidence_extractions_are_flagged(self) -> None:
        prepared = prepare_extracted_invoice(
            {
                "fields": {
                    "vendor": "Example Studio",
                    "total_amount": "125.00",
                    "currency": "USD",
                },
                "confidence": {
                    "vendor": 0.98,
                    "total_amount": 0.6,
                    "currency": 0.95,
                },
            }
        )
        self.assertIsNone(prepared["fields"]["issue_date"])
        self.assertIn("issue_date", prepared["review_fields"])
        self.assertIn("total_amount", prepared["review_fields"])
        self.assertNotIn("vendor", prepared["review_fields"])

    def test_invalid_extracted_values_are_reviewed_not_silently_accepted(self) -> None:
        prepared = prepare_extracted_invoice(
            {
                "fields": {
                    "issue_date": "next Tuesday",
                    "total_amount": "-42.00",
                },
                "confidence": {"issue_date": 0.99, "total_amount": 0.99},
            }
        )
        self.assertIn("issue_date", prepared["review_fields"])
        self.assertIn("total_amount", prepared["review_fields"])
        self.assertEqual(len(prepared["warnings"]), 2)


if __name__ == "__main__":
    unittest.main()
