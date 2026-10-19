"""SQLite storage for confirmed invoices and user-entered transactions."""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from pocketcfo.validation import (
    InputValidationError,
    parse_iso_date,
    validate_invoice_input,
    validate_transaction_input,
)


DEFAULT_DATABASE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "pocketcfo.sqlite3"
)


class DuplicateRecordError(ValueError):
    """A matching invoice or transaction is already stored."""


@contextmanager
def _connection(database_path: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
    """Create the local database schema if it does not already exist."""
    with _connection(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS invoices (
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
                paid_date TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS invoices_vendor_number_unique
            ON invoices(lower(trim(vendor)), lower(trim(invoice_number)))
            WHERE invoice_number IS NOT NULL AND trim(invoice_number) <> '';

            CREATE UNIQUE INDEX IF NOT EXISTS invoices_document_hash_unique
            ON invoices(document_sha256)
            WHERE document_sha256 IS NOT NULL;

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
                transaction_date TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT,
                amount TEXT NOT NULL,
                currency TEXT NOT NULL,
                invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS transactions_date_index
            ON transactions(transaction_date);

            CREATE UNIQUE INDEX IF NOT EXISTS transactions_invoice_unique
            ON transactions(invoice_id)
            WHERE invoice_id IS NOT NULL;

            CREATE UNIQUE INDEX IF NOT EXISTS transactions_exact_duplicate_unique
            ON transactions(
                kind,
                transaction_date,
                lower(trim(description)),
                amount,
                currency,
                ifnull(invoice_id, -1)
            );
            """
        )
        invoice_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(invoices)").fetchall()
        }
        if "paid_date" not in invoice_columns:
            connection.execute("ALTER TABLE invoices ADD COLUMN paid_date TEXT")


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_invoices(database_path: str | Path = DEFAULT_DATABASE_PATH) -> list[dict[str, Any]]:
    with _connection(database_path) as connection:
        rows = connection.execute(
            "SELECT * FROM invoices ORDER BY COALESCE(issue_date, created_at) DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_invoice(
    invoice_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> dict[str, Any] | None:
    with _connection(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
    return _row_to_dict(row)


def find_invoice_duplicate(
    fields: dict[str, Any],
    *,
    document_sha256: str | None = None,
    exclude_id: int | None = None,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> dict[str, Any] | None:
    """Find a saved invoice with the same vendor/number or exact PDF hash."""
    normalized = validate_invoice_input(fields)
    clauses = []
    parameters: list[Any] = []

    if normalized["invoice_number"]:
        clauses.append(
            "lower(trim(vendor)) = lower(trim(?)) "
            "AND lower(trim(invoice_number)) = lower(trim(?))"
        )
        parameters.extend([normalized["vendor"], normalized["invoice_number"]])
    if document_sha256:
        clauses.append("document_sha256 = ?")
        parameters.append(document_sha256)
    if not clauses:
        return None

    query = f"SELECT * FROM invoices WHERE ({' OR '.join(clauses)})"
    if exclude_id is not None:
        query += " AND id <> ?"
        parameters.append(exclude_id)
    query += " ORDER BY id LIMIT 1"

    with _connection(database_path) as connection:
        row = connection.execute(query, parameters).fetchone()
    return _row_to_dict(row)


def save_invoice(
    fields: dict[str, Any],
    *,
    document_sha256: str | None = None,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    """Save a human-confirmed invoice after validation and duplicate checking."""
    normalized = validate_invoice_input(fields)
    duplicate = find_invoice_duplicate(
        normalized,
        document_sha256=document_sha256,
        database_path=database_path,
    )
    if duplicate:
        raise DuplicateRecordError(
            f"This looks like invoice #{duplicate['id']} already saved "
            f"for {duplicate['vendor']}."
        )

    timestamp = _timestamp()
    try:
        with _connection(database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO invoices (
                    vendor, invoice_number, issue_date, due_date, currency,
                    total_amount, tax_amount, notes, document_sha256,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized["vendor"],
                    normalized["invoice_number"],
                    normalized["issue_date"],
                    normalized["due_date"],
                    normalized["currency"],
                    str(normalized["total_amount"]),
                    str(normalized["tax_amount"])
                    if normalized["tax_amount"] is not None
                    else None,
                    normalized["notes"],
                    document_sha256,
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)
    except sqlite3.IntegrityError as error:
        raise DuplicateRecordError(
            "This invoice conflicts with an invoice that was just saved."
        ) from error


def update_invoice(
    invoice_id: int,
    fields: dict[str, Any],
    *,
    document_sha256: str | None = None,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    """Update a saved invoice without allowing it to duplicate another invoice."""
    normalized = validate_invoice_input(fields)
    existing = get_invoice(invoice_id, database_path)
    if existing is None:
        raise ValueError("The invoice to edit no longer exists.")

    if document_sha256 is None:
        document_sha256 = existing["document_sha256"]
    duplicate = find_invoice_duplicate(
        normalized,
        document_sha256=document_sha256,
        exclude_id=invoice_id,
        database_path=database_path,
    )
    if duplicate:
        raise DuplicateRecordError(
            f"This matches invoice #{duplicate['id']} already saved "
            f"for {duplicate['vendor']}."
        )
    if existing["paid_date"] and (
        normalized["currency"] != existing["currency"]
        or normalized["total_amount"] != Decimal(existing["total_amount"])
    ):
        raise ValueError(
            "This invoice has a confirmed payment. Delete its linked income "
            "transaction before changing the invoice total or currency."
        )

    try:
        with _connection(database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE invoices
                SET vendor = ?, invoice_number = ?, issue_date = ?, due_date = ?,
                    currency = ?, total_amount = ?, tax_amount = ?, notes = ?,
                    document_sha256 = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    normalized["vendor"],
                    normalized["invoice_number"],
                    normalized["issue_date"],
                    normalized["due_date"],
                    normalized["currency"],
                    str(normalized["total_amount"]),
                    str(normalized["tax_amount"])
                    if normalized["tax_amount"] is not None
                    else None,
                    normalized["notes"],
                    document_sha256,
                    _timestamp(),
                    invoice_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("The invoice to edit no longer exists.")
    except sqlite3.IntegrityError as error:
        raise DuplicateRecordError(
            "This invoice conflicts with an invoice that was just saved."
        ) from error


def delete_invoice(
    invoice_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    with _connection(database_path) as connection:
        connection.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))


def list_transactions(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[dict[str, Any]]:
    with _connection(database_path) as connection:
        rows = connection.execute(
            "SELECT * FROM transactions ORDER BY transaction_date DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_transaction(
    transaction_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> dict[str, Any] | None:
    with _connection(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
    return _row_to_dict(row)


def _find_transaction_duplicate(
    fields: dict[str, Any],
    *,
    exclude_id: int | None,
    database_path: str | Path,
) -> dict[str, Any] | None:
    with _connection(database_path) as connection:
        query = """
            SELECT * FROM transactions
            WHERE kind = ? AND transaction_date = ? AND lower(trim(description)) = lower(trim(?))
                AND amount = ? AND currency = ? AND invoice_id IS ?
        """
        parameters: list[Any] = [
            fields["kind"],
            fields["transaction_date"],
            fields["description"],
            str(fields["amount"]),
            fields["currency"],
            fields["invoice_id"],
        ]
        if exclude_id is not None:
            query += " AND id <> ?"
            parameters.append(exclude_id)
        query += " ORDER BY id LIMIT 1"
        row = connection.execute(query, parameters).fetchone()
    return _row_to_dict(row)


def save_transaction(
    fields: dict[str, Any],
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    """Save one manually entered transaction after validation."""
    normalized = validate_transaction_input(fields)
    if _find_transaction_duplicate(
        normalized,
        exclude_id=None,
        database_path=database_path,
    ):
        raise DuplicateRecordError("An identical transaction is already saved.")

    timestamp = _timestamp()
    try:
        with _connection(database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO transactions (
                    kind, transaction_date, description, category, amount,
                    currency, invoice_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized["kind"],
                    normalized["transaction_date"],
                    normalized["description"],
                    normalized["category"],
                    str(normalized["amount"]),
                    normalized["currency"],
                    normalized["invoice_id"],
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)
    except sqlite3.IntegrityError as error:
        if "transactions.invoice_id" in str(error):
            raise DuplicateRecordError(
                "A transaction is already linked to this invoice."
            ) from error
        if "transactions_exact_duplicate_unique" in str(error):
            raise DuplicateRecordError("An identical transaction is already saved.") from error
        raise


def update_transaction(
    transaction_id: int,
    fields: dict[str, Any],
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    """Update an existing transaction without creating an identical duplicate."""
    normalized = validate_transaction_input(fields)
    existing_transaction = get_transaction(transaction_id, database_path)
    if existing_transaction is None:
        raise ValueError("The transaction to edit no longer exists.")
    paid_invoice_id = None
    if existing_transaction["invoice_id"] is not None:
        invoice = get_invoice(existing_transaction["invoice_id"], database_path)
        if invoice and invoice["paid_date"]:
            if (
                normalized["kind"] != "income"
                or normalized["currency"] != invoice["currency"]
                or normalized["amount"] != Decimal(invoice["total_amount"])
            ):
                raise InputValidationError(
                    "A confirmed invoice payment must match its invoice amount and "
                    "currency. Delete the linked transaction to undo payment first."
                )
            paid_invoice_id = invoice["id"]
    if _find_transaction_duplicate(
        normalized,
        exclude_id=transaction_id,
        database_path=database_path,
    ):
        raise DuplicateRecordError("An identical transaction is already saved.")

    try:
        with _connection(database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE transactions
                SET kind = ?, transaction_date = ?, description = ?, category = ?,
                    amount = ?, currency = ?, invoice_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    normalized["kind"],
                    normalized["transaction_date"],
                    normalized["description"],
                    normalized["category"],
                    str(normalized["amount"]),
                    normalized["currency"],
                    normalized["invoice_id"],
                    _timestamp(),
                    transaction_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("The transaction to edit no longer exists.")
            if paid_invoice_id is not None:
                connection.execute(
                    """
                    UPDATE invoices
                    SET paid_date = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        normalized["transaction_date"],
                        _timestamp(),
                        paid_invoice_id,
                    ),
                )
    except sqlite3.IntegrityError as error:
        if "transactions.invoice_id" in str(error):
            raise DuplicateRecordError(
                "A transaction is already linked to this invoice."
            ) from error
        if "transactions_exact_duplicate_unique" in str(error):
            raise DuplicateRecordError("An identical transaction is already saved.") from error
        raise


def delete_transaction(
    transaction_id: int,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    with _connection(database_path) as connection:
        transaction = connection.execute(
            "SELECT kind, invoice_id FROM transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
        if transaction is None:
            return
        connection.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        if transaction["kind"] == "income" and transaction["invoice_id"] is not None:
            connection.execute(
                """
                UPDATE invoices
                SET paid_date = NULL, updated_at = ?
                WHERE id = ? AND paid_date IS NOT NULL
                """,
                (_timestamp(), transaction["invoice_id"]),
            )


def record_invoice_payment(
    invoice_id: int,
    payment_date: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> int:
    """Confirm payment and create its linked income in one SQLite transaction."""
    normalized_date = parse_iso_date(
        payment_date,
        field_name="payment date",
        required=True,
    )
    timestamp = _timestamp()
    try:
        with _connection(database_path) as connection:
            invoice = connection.execute(
                "SELECT * FROM invoices WHERE id = ?",
                (invoice_id,),
            ).fetchone()
            if invoice is None:
                raise ValueError("The invoice to mark as paid no longer exists.")
            if invoice["paid_date"]:
                raise DuplicateRecordError("This invoice is already marked as paid.")
            linked_transaction = connection.execute(
                "SELECT * FROM transactions WHERE invoice_id = ?",
                (invoice_id,),
            ).fetchone()

            transaction = validate_transaction_input(
                {
                    "kind": "income",
                    "transaction_date": normalized_date,
                    "description": (
                        f"Invoice payment: {invoice['vendor']}"
                        + (
                            f" ({invoice['invoice_number']})"
                            if invoice["invoice_number"]
                            else ""
                        )
                    ),
                    "category": "Invoice payment",
                    "amount": invoice["total_amount"],
                    "currency": invoice["currency"],
                    "invoice_id": invoice_id,
                }
            )
            if linked_transaction is not None:
                if (
                    linked_transaction["kind"] != "income"
                    or linked_transaction["currency"] != transaction["currency"]
                    or Decimal(linked_transaction["amount"]) != transaction["amount"]
                ):
                    raise DuplicateRecordError(
                        "The linked transaction does not match this invoice as an "
                        "income payment. Correct or delete it before confirming payment."
                    )
                connection.execute(
                    """
                    UPDATE transactions
                    SET transaction_date = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (normalized_date, timestamp, linked_transaction["id"]),
                )
                connection.execute(
                    "UPDATE invoices SET paid_date = ?, updated_at = ? WHERE id = ?",
                    (normalized_date, timestamp, invoice_id),
                )
                return int(linked_transaction["id"])

            cursor = connection.execute(
                """
                INSERT INTO transactions (
                    kind, transaction_date, description, category, amount,
                    currency, invoice_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction["kind"],
                    transaction["transaction_date"],
                    transaction["description"],
                    transaction["category"],
                    str(transaction["amount"]),
                    transaction["currency"],
                    transaction["invoice_id"],
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                "UPDATE invoices SET paid_date = ?, updated_at = ? WHERE id = ?",
                (normalized_date, timestamp, invoice_id),
            )
            return int(cursor.lastrowid)
    except sqlite3.IntegrityError as error:
        raise DuplicateRecordError(
            "A transaction is already linked to this invoice or duplicates an "
            "existing transaction."
        ) from error
