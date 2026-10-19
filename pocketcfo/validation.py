"""Input validation for invoice and transaction fields."""

from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Any


INVOICE_FIELDS = (
    "vendor",
    "invoice_number",
    "issue_date",
    "due_date",
    "currency",
    "total_amount",
    "tax_amount",
)
CONFIDENCE_THRESHOLD = 0.75

_ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CURRENCY_PATTERN = re.compile(r"^[A-Za-z]{3}$")
_AMOUNT_PATTERN = re.compile(r"^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?$")


class InputValidationError(ValueError):
    """A user-entered financial value is not valid."""


def parse_amount(value: Any, *, required: bool = False) -> Decimal | None:
    """Parse a non-negative monetary value with no more than two decimals."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise InputValidationError("Enter an amount before saving.")
        return None
    if isinstance(value, bool):
        raise InputValidationError("Enter a valid non-negative amount.")

    amount_text = str(value).strip()
    if len(amount_text) > 64:
        raise InputValidationError("The amount is too long to be a valid invoice value.")
    if not _AMOUNT_PATTERN.fullmatch(amount_text):
        raise InputValidationError(
            "Use digits with an optional decimal point and up to two decimal places."
        )

    try:
        amount = Decimal(amount_text.replace(",", ""))
    except InvalidOperation as error:
        raise InputValidationError("Enter a valid amount.") from error

    if not amount.is_finite() or amount < 0:
        raise InputValidationError("Amount must be a finite, non-negative number.")
    try:
        return amount.quantize(Decimal("0.01"))
    except InvalidOperation as error:
        raise InputValidationError("The amount is too large to save safely.") from error


def parse_iso_date(value: Any, *, field_name: str, required: bool = False) -> str | None:
    """Validate a calendar date written as YYYY-MM-DD."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise InputValidationError(f"Enter the {field_name}.")
        return None
    if not isinstance(value, str) or not _ISO_DATE_PATTERN.fullmatch(value.strip()):
        raise InputValidationError(f"Enter {field_name} as YYYY-MM-DD.")

    date_text = value.strip()
    try:
        date.fromisoformat(date_text)
    except ValueError as error:
        raise InputValidationError(
            f"The {field_name} is not a valid calendar date."
        ) from error
    return date_text


def validate_currency(value: Any, *, required: bool = False) -> str | None:
    """Validate a three-letter ISO currency code without guessing one."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise InputValidationError("Enter the currency code, such as USD.")
        return None
    if not isinstance(value, str) or not _CURRENCY_PATTERN.fullmatch(value.strip()):
        raise InputValidationError("Currency must be a three-letter code, such as USD.")
    return value.strip().upper()


def validate_invoice_input(fields: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize values submitted on the invoice review form."""
    vendor = str(fields.get("vendor") or "").strip()
    if not vendor:
        raise InputValidationError("Enter the vendor or supplier name.")

    invoice_number = str(fields.get("invoice_number") or "").strip() or None
    issue_date = parse_iso_date(fields.get("issue_date"), field_name="issue date")
    due_date = parse_iso_date(fields.get("due_date"), field_name="due date")
    currency = validate_currency(fields.get("currency"), required=True)
    total_amount = parse_amount(fields.get("total_amount"), required=True)
    tax_amount = parse_amount(fields.get("tax_amount"))
    notes = str(fields.get("notes") or "").strip() or None

    if len(vendor) > 200:
        raise InputValidationError("Vendor name must be 200 characters or fewer.")
    if invoice_number is not None and len(invoice_number) > 100:
        raise InputValidationError("Invoice number must be 100 characters or fewer.")
    if notes is not None and len(notes) > 2000:
        raise InputValidationError("Notes must be 2,000 characters or fewer.")

    return {
        "vendor": vendor,
        "invoice_number": invoice_number,
        "issue_date": issue_date,
        "due_date": due_date,
        "currency": currency,
        "total_amount": total_amount,
        "tax_amount": tax_amount,
        "notes": notes,
    }


def validate_transaction_input(fields: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one manually entered transaction."""
    kind = str(fields.get("kind") or "").strip().lower()
    if kind not in {"income", "expense"}:
        raise InputValidationError("Choose income or expense.")

    description = str(fields.get("description") or "").strip()
    if not description:
        raise InputValidationError("Enter a transaction description.")
    if len(description) > 200:
        raise InputValidationError(
            "Transaction description must be 200 characters or fewer."
        )

    amount = parse_amount(fields.get("amount"), required=True)
    if amount == 0:
        raise InputValidationError("Transaction amount must be greater than zero.")

    category = str(fields.get("category") or "").strip() or None
    if category is not None and len(category) > 100:
        raise InputValidationError("Category must be 100 characters or fewer.")

    invoice_id = fields.get("invoice_id")
    if invoice_id in ("", None):
        invoice_id = None
    elif isinstance(invoice_id, bool) or not isinstance(invoice_id, int) or invoice_id < 1:
        raise InputValidationError("The linked invoice selection is not valid.")

    return {
        "kind": kind,
        "transaction_date": parse_iso_date(
            fields.get("transaction_date"),
            field_name="transaction date",
            required=True,
        ),
        "description": description,
        "category": category,
        "amount": amount,
        "currency": validate_currency(fields.get("currency"), required=True),
        "invoice_id": invoice_id,
    }


def invoice_transaction_defaults(
    invoice: dict[str, Any],
    kind: str | None,
) -> dict[str, Any]:
    """Build an editable transaction draft from a confirmed invoice."""
    if kind not in {"income", "expense"}:
        raise InputValidationError("Choose income or expense.")

    return {
        "kind": kind,
        "transaction_date": invoice.get("issue_date") or "",
        "description": invoice["vendor"],
        "category": "",
        "amount": invoice["total_amount"],
        "currency": invoice["currency"],
        "invoice_id": invoice["id"],
    }


def prepare_extracted_invoice(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize model output and identify fields that need human review."""
    raw_fields = payload.get("fields", payload)
    if not isinstance(raw_fields, dict):
        raise InputValidationError("The model response did not contain invoice fields.")

    raw_confidence = payload.get("confidence", {})
    if not isinstance(raw_confidence, dict):
        raw_confidence = {}

    normalized: dict[str, Any] = {}
    confidence: dict[str, float] = {}
    review_fields: list[str] = []
    warnings: list[str] = []

    for field in INVOICE_FIELDS:
        value = raw_fields.get(field)
        if value is not None and not isinstance(value, (str, int, float)):
            warnings.append(f"{field.replace('_', ' ').title()} was not plain text.")
            value = None
        if isinstance(value, bool):
            value = None
        if value is not None:
            value = str(value).strip() or None
        normalized[field] = value

        raw_score = raw_confidence.get(field, 0)
        if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
            score = 0.0
        else:
            score = float(raw_score)
            if not 0 <= score <= 1:
                score = 0.0
        confidence[field] = score

        if value is None:
            review_fields.append(field)
        elif score < CONFIDENCE_THRESHOLD:
            review_fields.append(field)

    for field, parser, label in (
        ("issue_date", lambda value: parse_iso_date(value, field_name="issue date"), "Issue date"),
        ("due_date", lambda value: parse_iso_date(value, field_name="due date"), "Due date"),
        ("currency", lambda value: validate_currency(value), "Currency"),
        ("total_amount", lambda value: parse_amount(value), "Total amount"),
        ("tax_amount", lambda value: parse_amount(value), "Tax amount"),
    ):
        value = normalized[field]
        if value is None:
            continue
        try:
            parser(value)
        except InputValidationError as error:
            if field not in review_fields:
                review_fields.append(field)
            warnings.append(f"{label} needs correction: {error}")

    return {
        "fields": normalized,
        "confidence": confidence,
        "review_fields": review_fields,
        "warnings": warnings,
    }
