import unittest
from datetime import date

from pocketcfo.reports import (
    currency_summary,
    dashboard_summary,
    filter_records_by_period,
    invoice_status,
    invoices_to_csv,
    monthly_cashflow,
    spending_by_category,
    transactions_to_csv,
)


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transactions = [
            {
                "id": 1,
                "kind": "income",
                "transaction_date": "2025-01-10",
                "description": "Client payment",
                "category": "Services",
                "amount": "100.00",
                "currency": "USD",
                "invoice_id": None,
            },
            {
                "id": 2,
                "kind": "expense",
                "transaction_date": "2025-01-12",
                "description": "Software",
                "category": "Tools",
                "amount": "25.00",
                "currency": "USD",
                "invoice_id": None,
            },
            {
                "id": 3,
                "kind": "income",
                "transaction_date": "2025-01-15",
                "description": "Client payment",
                "category": "Services",
                "amount": "200.00",
                "currency": "EUR",
                "invoice_id": None,
            },
        ]

    def test_currency_totals_are_not_combined(self) -> None:
        summary = currency_summary(self.transactions).set_index("currency")
        self.assertEqual(summary.loc["USD", "income"], 100)
        self.assertEqual(summary.loc["USD", "expenses"], 25)
        self.assertEqual(summary.loc["USD", "net"], 75)
        self.assertEqual(summary.loc["EUR", "net"], 200)

    def test_monthly_cashflow_filters_to_one_currency(self) -> None:
        monthly = monthly_cashflow(self.transactions, "USD")
        self.assertEqual(len(monthly), 2)
        self.assertEqual(set(monthly["kind"]), {"income", "expense"})

    def test_spending_by_category_groups_only_expenses_in_one_currency(self) -> None:
        transactions = self.transactions + [
            {
                "kind": "expense",
                "category": None,
                "amount": "5.00",
                "currency": "USD",
            }
        ]
        result = spending_by_category(transactions, "USD").set_index("category")
        self.assertEqual(result.loc["Tools", "amount"], 25)
        self.assertEqual(result.loc["Uncategorized", "amount"], 5)
        self.assertNotIn("EUR", result.index)

    def test_date_filters_cover_calendar_periods_and_all_time(self) -> None:
        transactions = [
            {"transaction_date": "2025-01-01", "amount": "10"},
            {"transaction_date": "2025-02-28", "amount": "20"},
            {"transaction_date": "2025-03-01", "amount": "30"},
            {"transaction_date": None, "amount": "40"},
        ]
        today = date(2025, 3, 15)

        self.assertEqual(
            [item["amount"] for item in filter_records_by_period(
                transactions, "transaction_date", "This Month", today=today
            )],
            ["30"],
        )
        self.assertEqual(
            [item["amount"] for item in filter_records_by_period(
                transactions, "transaction_date", "Last Month", today=today
            )],
            ["20"],
        )
        self.assertEqual(
            [item["amount"] for item in filter_records_by_period(
                transactions, "transaction_date", "This Year", today=today
            )],
            ["10", "20", "30"],
        )
        self.assertEqual(
            len(filter_records_by_period(
                transactions, "transaction_date", "All Time", today=today
            )),
            4,
        )
        self.assertEqual(
            [item["amount"] for item in filter_records_by_period(
                transactions,
                "transaction_date",
                "Custom Range",
                start_date=date(2025, 2, 1),
                end_date=date(2025, 2, 28),
            )],
            ["20"],
        )
        with self.assertRaisesRegex(ValueError, "start and end"):
            filter_records_by_period(
                transactions,
                "transaction_date",
                "Custom Range",
            )

    def test_dashboard_summarizes_cash_and_invoice_status_without_mixing_currency(self) -> None:
        summary = dashboard_summary(
            [
                {
                    "currency": "USD",
                    "total_amount": "50.00",
                    "due_date": "2025-01-31",
                    "paid_date": None,
                },
                {
                    "currency": "EUR",
                    "total_amount": "80.00",
                    "due_date": "2025-03-01",
                    "paid_date": None,
                },
                {
                    "currency": "USD",
                    "total_amount": "20.00",
                    "due_date": "2025-01-01",
                    "paid_date": "2025-01-20",
                },
            ],
            self.transactions,
            today=date(2025, 2, 1),
        )
        self.assertEqual(summary["invoice_count"], 3)
        self.assertEqual(
            summary["currencies"],
            {
                "USD": {
                    "income": 100,
                    "expenses": 25,
                    "net": 75,
                },
                "EUR": {
                    "income": 200,
                    "expenses": 0,
                    "net": 200,
                },
            },
        )
        self.assertEqual(summary["outstanding_by_currency"], {"EUR": 80, "USD": 50})
        self.assertEqual(summary["overdue_count"], 1)
        self.assertEqual(summary["overdue_by_currency"], {"USD": 50})
        self.assertEqual(
            invoice_status(
                {
                    "due_date": "2025-01-01",
                    "paid_date": "2025-01-02",
                },
                today=date(2025, 2, 1),
            ),
            "Paid",
        )

    def test_csv_exports_have_headers_and_no_pdf_hash(self) -> None:
        transaction_csv = transactions_to_csv(self.transactions)
        invoice_csv = invoices_to_csv(
            [
                {
                    "id": 4,
                    "vendor": "Synthetic Client",
                    "invoice_number": "SAMPLE-1",
                    "issue_date": None,
                    "due_date": None,
                    "currency": "USD",
                    "total_amount": "50.00",
                    "tax_amount": None,
                    "notes": None,
                    "document_sha256": "must-not-export",
                    "paid_date": None,
                }
            ]
        )
        self.assertIn("transaction_date", transaction_csv)
        self.assertIn("vendor", invoice_csv)
        self.assertIn("status", invoice_csv)
        self.assertNotIn("must-not-export", invoice_csv)


if __name__ == "__main__":
    unittest.main()
