"""Analytics data preparation and in-memory CSV exports."""

from datetime import date, timedelta
from io import StringIO
from decimal import Decimal
from typing import Any

import pandas as pd


DATE_FILTERS = ("This Month", "Last Month", "This Year", "All Time", "Custom Range")


def invoice_status(invoice: dict[str, Any], *, today: date | None = None) -> str:
    """Derive invoice status from explicit payment confirmation and its due date."""
    if invoice.get("paid_date"):
        return "Paid"
    due_date = invoice.get("due_date")
    if due_date and date.fromisoformat(str(due_date)) < (today or date.today()):
        return "Overdue"
    return "Unpaid"


def filter_records_by_period(
    records: list[dict[str, Any]],
    date_field: str,
    period: str,
    *,
    today: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    """Filter saved records by a calendar period; undated records remain All Time."""
    if period not in DATE_FILTERS:
        raise ValueError(f"Unsupported date filter: {period}")
    if period == "All Time":
        return list(records)

    if period == "Custom Range":
        if start_date is None or end_date is None:
            raise ValueError("Custom date ranges require a start and end date.")
        if end_date < start_date:
            raise ValueError("The custom date range ends before it starts.")
        start, end = start_date, end_date
    else:
        current_date = today or date.today()
        if period == "This Month":
            start = current_date.replace(day=1)
            end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        elif period == "Last Month":
            this_month = current_date.replace(day=1)
            end = this_month - timedelta(days=1)
            start = end.replace(day=1)
        else:
            start = current_date.replace(month=1, day=1)
            end = current_date.replace(month=12, day=31)

    selected = []
    for record in records:
        value = record.get(date_field)
        if not value:
            continue
        record_date = date.fromisoformat(str(value))
        if start <= record_date <= end:
            selected.append(record)
    return selected


def currency_summary(transactions: list[dict[str, Any]]) -> pd.DataFrame:
    """Return income, expenses, and net amounts grouped by currency."""
    columns = ["currency", "income", "expenses", "net"]
    totals: dict[str, dict[str, Decimal]] = {}
    for transaction in transactions:
        currency = transaction["currency"]
        if currency not in totals:
            totals[currency] = {
                "income": Decimal("0.00"),
                "expenses": Decimal("0.00"),
            }
        total_field = "income" if transaction["kind"] == "income" else "expenses"
        totals[currency][total_field] += Decimal(str(transaction["amount"]))

    rows = [
        {
            "currency": currency,
            "income": values["income"],
            "expenses": values["expenses"],
            "net": values["income"] - values["expenses"],
        }
        for currency, values in sorted(totals.items())
    ]
    return pd.DataFrame(rows, columns=columns)


def dashboard_summary(
    invoices: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Calculate dashboard totals from transactions without mixing currencies."""
    totals = {
        row["currency"]: {
            "income": row["income"],
            "expenses": row["expenses"],
            "net": row["net"],
        }
        for row in currency_summary(transactions).to_dict(orient="records")
    }
    outstanding: dict[str, Decimal] = {}
    overdue: dict[str, Decimal] = {}
    overdue_count = 0
    for invoice in invoices:
        if invoice_status(invoice, today=today) == "Paid":
            continue
        currency = invoice["currency"]
        amount = Decimal(str(invoice["total_amount"]))
        outstanding[currency] = outstanding.get(currency, Decimal("0.00")) + amount
        if invoice_status(invoice, today=today) == "Overdue":
            overdue_count += 1
            overdue[currency] = overdue.get(currency, Decimal("0.00")) + amount

    return {
        "currencies": totals,
        "invoice_count": len(invoices),
        "outstanding_by_currency": dict(sorted(outstanding.items())),
        "overdue_count": overdue_count,
        "overdue_by_currency": dict(sorted(overdue.items())),
    }


def monthly_cashflow(
    transactions: list[dict[str, Any]],
    currency: str,
) -> pd.DataFrame:
    """Return monthly income and expenses for one currency only."""
    columns = ["month", "kind", "amount"]
    totals: dict[tuple[str, str], Decimal] = {}
    for transaction in transactions:
        if transaction["currency"] != currency:
            continue
        month = pd.Period(transaction["transaction_date"], freq="M").strftime("%Y-%m")
        key = (month, transaction["kind"])
        totals[key] = totals.get(key, Decimal("0.00")) + Decimal(
            str(transaction["amount"])
        )
    rows = [
        {"month": month, "kind": kind, "amount": amount}
        for (month, kind), amount in sorted(totals.items())
    ]
    return pd.DataFrame(rows, columns=columns)


def spending_by_category(
    transactions: list[dict[str, Any]],
    currency: str,
) -> pd.DataFrame:
    """Return expenses grouped by category for exactly one currency."""
    totals: dict[str, Decimal] = {}
    for transaction in transactions:
        if transaction["kind"] != "expense" or transaction["currency"] != currency:
            continue
        category = transaction.get("category") or "Uncategorized"
        totals[category] = totals.get(category, Decimal("0.00")) + Decimal(
            str(transaction["amount"])
        )
    return pd.DataFrame(
        [
            {"category": category, "amount": amount}
            for category, amount in sorted(totals.items())
        ],
        columns=["category", "amount"],
    )


def transactions_to_csv(transactions: list[dict[str, Any]]) -> str:
    """Create a downloadable CSV string without writing a file."""
    columns = [
        "id",
        "kind",
        "transaction_date",
        "description",
        "category",
        "amount",
        "currency",
        "invoice_id",
    ]
    return pd.DataFrame(transactions, columns=columns).to_csv(index=False)


def invoices_to_csv(invoices: list[dict[str, Any]]) -> str:
    """Create a downloadable CSV string without sensitive PDF contents."""
    columns = [
        "id",
        "vendor",
        "invoice_number",
        "issue_date",
        "due_date",
        "currency",
        "total_amount",
        "tax_amount",
        "paid_date",
        "notes",
    ]
    output = StringIO()
    frame = pd.DataFrame(invoices)
    if "paid_date" not in frame:
        frame["paid_date"] = None
    if not frame.empty:
        frame["status"] = frame.apply(
            lambda row: invoice_status(row.to_dict()),
            axis=1,
        )
    else:
        frame["status"] = pd.Series(dtype="object")
    pd.DataFrame(frame, columns=columns + ["status"]).to_csv(output, index=False)
    return output.getvalue()
