import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pocketcfo.database import (
    DuplicateRecordError,
    delete_invoice,
    delete_transaction,
    initialize_database,
    list_invoices,
    list_transactions,
    record_invoice_payment,
    save_invoice,
    save_transaction,
    update_invoice,
    update_transaction,
)
from pocketcfo.validation import InputValidationError


class SQLiteRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.sqlite3"
        initialize_database(self.database_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def invoice(self, **changes: str) -> dict[str, str]:
        fields = {
            "vendor": "Example Studio",
            "invoice_number": "INV-001",
            "issue_date": "2025-01-02",
            "currency": "USD",
            "total_amount": "100.00",
            "tax_amount": "",
        }
        fields.update(changes)
        return fields

    def transaction(self, **changes: str) -> dict[str, str]:
        fields = {
            "kind": "income",
            "transaction_date": "2025-01-10",
            "description": "Invoice payment",
            "category": "Client work",
            "amount": "100.00",
            "currency": "USD",
        }
        fields.update(changes)
        return fields

    def test_saves_only_valid_invoice_records_and_detects_duplicate(self) -> None:
        invoice_id = save_invoice(self.invoice(), database_path=self.database_path)
        self.assertEqual(len(list_invoices(self.database_path)), 1)
        with self.assertRaises(DuplicateRecordError):
            save_invoice(
                self.invoice(vendor=" example studio ", invoice_number="inv-001"),
                database_path=self.database_path,
            )
        with self.assertRaises(InputValidationError):
            save_invoice(
                self.invoice(total_amount="not a number"),
                database_path=self.database_path,
            )
        self.assertEqual(list_invoices(self.database_path)[0]["id"], invoice_id)

    def test_detects_same_pdf_hash_even_if_invoice_number_is_missing(self) -> None:
        save_invoice(
            self.invoice(invoice_number=""),
            document_sha256="synthetic-hash",
            database_path=self.database_path,
        )
        with self.assertRaises(DuplicateRecordError):
            save_invoice(
                self.invoice(invoice_number=""),
                document_sha256="synthetic-hash",
                database_path=self.database_path,
            )

    def test_edits_and_deletes_invoice(self) -> None:
        invoice_id = save_invoice(self.invoice(), database_path=self.database_path)
        update_invoice(
            invoice_id,
            self.invoice(vendor="Updated Studio", invoice_number="INV-002"),
            database_path=self.database_path,
        )
        self.assertEqual(
            list_invoices(self.database_path)[0]["vendor"],
            "Updated Studio",
        )
        delete_invoice(invoice_id, self.database_path)
        self.assertEqual(list_invoices(self.database_path), [])

    def test_transaction_duplicate_edit_delete_and_invoice_link(self) -> None:
        invoice_id = save_invoice(self.invoice(), database_path=self.database_path)
        values = self.transaction(invoice_id=invoice_id)
        transaction_id = save_transaction(values, self.database_path)
        with self.assertRaises(DuplicateRecordError):
            save_transaction(values, self.database_path)

        changed = self.transaction(
            invoice_id=invoice_id,
            description="Revised invoice payment",
            amount="110.00",
        )
        update_transaction(transaction_id, changed, self.database_path)
        self.assertEqual(
            list_transactions(self.database_path)[0]["description"],
            "Revised invoice payment",
        )

        delete_invoice(invoice_id, self.database_path)
        self.assertIsNone(list_transactions(self.database_path)[0]["invoice_id"])
        delete_transaction(transaction_id, self.database_path)
        self.assertEqual(list_transactions(self.database_path), [])

    def test_invoice_can_be_linked_to_only_one_transaction(self) -> None:
        invoice_id = save_invoice(self.invoice(), database_path=self.database_path)
        first = self.transaction(invoice_id=invoice_id)
        save_transaction(first, self.database_path)
        with self.assertRaisesRegex(DuplicateRecordError, "already linked"):
            save_transaction(
                self.transaction(
                    invoice_id=invoice_id,
                    kind="expense",
                    description="Different transaction",
                ),
                self.database_path,
            )
        self.assertEqual(len(list_transactions(self.database_path)), 1)

    def test_database_rejects_duplicate_even_if_precheck_races(self) -> None:
        values = self.transaction()
        save_transaction(values, self.database_path)
        with patch("pocketcfo.database._find_transaction_duplicate", return_value=None):
            with self.assertRaisesRegex(DuplicateRecordError, "identical transaction"):
                save_transaction(values, self.database_path)
        self.assertEqual(len(list_transactions(self.database_path)), 1)

    def test_edit_cannot_link_second_transaction_to_same_invoice(self) -> None:
        first_invoice_id = save_invoice(
            self.invoice(invoice_number="INV-001"),
            database_path=self.database_path,
        )
        second_invoice_id = save_invoice(
            self.invoice(invoice_number="INV-002"),
            database_path=self.database_path,
        )
        first_id = save_transaction(
            self.transaction(invoice_id=first_invoice_id),
            self.database_path,
        )
        second_id = save_transaction(
            self.transaction(
                invoice_id=second_invoice_id,
                description="Another payment",
            ),
            self.database_path,
        )

        with self.assertRaisesRegex(DuplicateRecordError, "already linked"):
            update_transaction(
                second_id,
                self.transaction(
                    invoice_id=first_invoice_id,
                    description="Updated payment",
                ),
                self.database_path,
            )

        linked_ids = {
            transaction["id"]: transaction["invoice_id"]
            for transaction in list_transactions(self.database_path)
        }
        self.assertEqual(linked_ids[first_id], first_invoice_id)
        self.assertEqual(linked_ids[second_id], second_invoice_id)

    def test_invoice_transaction_draft_can_be_saved_and_is_not_assumed_income(self) -> None:
        from pocketcfo.validation import invoice_transaction_defaults

        invoice_id = save_invoice(self.invoice(), database_path=self.database_path)
        saved_invoice = list_invoices(self.database_path)[0]
        draft = invoice_transaction_defaults(saved_invoice, "expense")
        transaction_id = save_transaction(draft, self.database_path)

        transaction = list_transactions(self.database_path)[0]
        self.assertEqual(transaction["id"], transaction_id)
        self.assertEqual(transaction["kind"], "expense")
        self.assertEqual(transaction["description"], "Example Studio")
        self.assertEqual(transaction["transaction_date"], "2025-01-02")
        self.assertEqual(transaction["invoice_id"], invoice_id)
        self.assertEqual(len(list_invoices(self.database_path)), 1)

    def test_payment_confirmation_atomically_marks_invoice_paid_and_creates_income(self) -> None:
        invoice_id = save_invoice(self.invoice(), database_path=self.database_path)

        transaction_id = record_invoice_payment(
            invoice_id,
            "2025-01-15",
            self.database_path,
        )

        invoice = list_invoices(self.database_path)[0]
        transaction = list_transactions(self.database_path)[0]
        self.assertEqual(invoice["paid_date"], "2025-01-15")
        self.assertEqual(transaction["id"], transaction_id)
        self.assertEqual(transaction["kind"], "income")
        self.assertEqual(transaction["amount"], "100.00")
        self.assertEqual(transaction["currency"], "USD")
        self.assertEqual(transaction["transaction_date"], "2025-01-15")
        self.assertEqual(transaction["invoice_id"], invoice_id)
        with self.assertRaisesRegex(DuplicateRecordError, "already marked as paid"):
            record_invoice_payment(invoice_id, "2025-01-15", self.database_path)

    def test_invalid_payment_rolls_back_and_deleting_payment_reopens_invoice(self) -> None:
        invoice_id = save_invoice(self.invoice(), database_path=self.database_path)
        with self.assertRaises(InputValidationError):
            record_invoice_payment(invoice_id, "not-a-date", self.database_path)
        self.assertIsNone(list_invoices(self.database_path)[0]["paid_date"])
        self.assertEqual(list_transactions(self.database_path), [])

        transaction_id = record_invoice_payment(
            invoice_id,
            "2025-01-15",
            self.database_path,
        )
        delete_transaction(transaction_id, self.database_path)
        self.assertIsNone(list_invoices(self.database_path)[0]["paid_date"])

    def test_payment_confirmation_reuses_matching_linked_income_without_duplication(self) -> None:
        invoice_id = save_invoice(self.invoice(), database_path=self.database_path)
        existing_id = save_transaction(
            self.transaction(
                invoice_id=invoice_id,
                transaction_date="2025-01-10",
            ),
            self.database_path,
        )

        confirmed_id = record_invoice_payment(
            invoice_id,
            "2025-01-15",
            self.database_path,
        )

        self.assertEqual(confirmed_id, existing_id)
        self.assertEqual(len(list_transactions(self.database_path)), 1)
        self.assertEqual(list_transactions(self.database_path)[0]["transaction_date"], "2025-01-15")
        self.assertEqual(list_invoices(self.database_path)[0]["paid_date"], "2025-01-15")

    def test_paid_invoice_amount_or_currency_cannot_diverge_from_linked_income(self) -> None:
        invoice_id = save_invoice(self.invoice(), database_path=self.database_path)
        record_invoice_payment(invoice_id, "2025-01-15", self.database_path)
        with self.assertRaisesRegex(ValueError, "confirmed payment"):
            update_invoice(
                invoice_id,
                self.invoice(total_amount="125.00"),
                database_path=self.database_path,
            )
        with self.assertRaisesRegex(InputValidationError, "must match its invoice"):
            update_transaction(
                list_transactions(self.database_path)[0]["id"],
                self.transaction(invoice_id=invoice_id, amount="125.00"),
                self.database_path,
            )
        self.assertEqual(list_invoices(self.database_path)[0]["total_amount"], "100.00")
        self.assertEqual(list_transactions(self.database_path)[0]["amount"], "100.00")

    def test_editing_confirmed_payment_date_keeps_invoice_paid_date_in_sync(self) -> None:
        invoice_id = save_invoice(self.invoice(), database_path=self.database_path)
        transaction_id = record_invoice_payment(
            invoice_id,
            "2025-01-15",
            self.database_path,
        )

        update_transaction(
            transaction_id,
            self.transaction(
                invoice_id=invoice_id,
                transaction_date="2025-01-20",
            ),
            self.database_path,
        )

        self.assertEqual(list_invoices(self.database_path)[0]["paid_date"], "2025-01-20")
        self.assertEqual(
            list_transactions(self.database_path)[0]["transaction_date"],
            "2025-01-20",
        )

    def test_initializes_legacy_database_with_non_destructive_paid_date_column(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.sqlite3"
        connection = sqlite3.connect(legacy_path)
        try:
            connection.execute(
                """
                CREATE TABLE invoices (
                    id INTEGER PRIMARY KEY,
                    vendor TEXT NOT NULL,
                    invoice_number TEXT,
                    issue_date TEXT,
                    due_date TEXT,
                    currency TEXT NOT NULL,
                    total_amount TEXT NOT NULL,
                    tax_amount TEXT,
                    notes TEXT,
                    document_sha256 TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO invoices (
                    vendor, invoice_number, currency, total_amount,
                    created_at, updated_at
                ) VALUES ('Legacy Studio', 'OLD-1', 'USD', '12.00', 'created', 'updated')
                """
            )
            connection.commit()
        finally:
            connection.close()

        initialize_database(legacy_path)

        invoice = list_invoices(legacy_path)[0]
        self.assertEqual(invoice["vendor"], "Legacy Studio")
        self.assertEqual(invoice["total_amount"], "12.00")
        self.assertIsNone(invoice["paid_date"])


if __name__ == "__main__":
    unittest.main()
