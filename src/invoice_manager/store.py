"""SQLite register of invoices."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id      TEXT NOT NULL,
    sender          TEXT,
    subject         TEXT,
    received_at     TEXT,              -- ISO datetime of the email
    filename        TEXT,
    file_path       TEXT,
    sha256          TEXT UNIQUE,       -- de-duplicates the same file sent twice
    vendor          TEXT,
    invoice_number  TEXT,
    invoice_date    TEXT,              -- ISO date
    amount          REAL,
    currency        TEXT,
    status          TEXT NOT NULL DEFAULT 'unpaid' CHECK (status IN ('unpaid', 'paid', 'ignored')),
    paid_on         TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id   TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

EDITABLE = {"vendor", "invoice_number", "invoice_date", "amount", "currency", "status", "paid_on", "notes"}

COLUMNS = [
    "id", "message_id", "sender", "subject", "received_at", "filename", "file_path", "sha256",
    "vendor", "invoice_number", "invoice_date", "amount", "currency", "status", "paid_on",
    "notes", "created_at",
]


@dataclass
class NewInvoice:
    message_id: str
    sender: str
    subject: str
    received_at: str
    filename: str
    file_path: str
    sha256: str
    vendor: str | None
    invoice_number: str | None
    invoice_date: date | None
    amount: float | None
    currency: str | None


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # -- messages -----------------------------------------------------------
    def is_processed(self, message_id: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,))
        return cur.fetchone() is not None

    def mark_processed(self, message_id: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)", (message_id,)
        )
        self.conn.commit()

    # -- invoices -----------------------------------------------------------
    def has_file(self, sha256: str) -> bool:
        return self.conn.execute("SELECT 1 FROM invoices WHERE sha256 = ?", (sha256,)).fetchone() is not None

    def add(self, inv: NewInvoice) -> int | None:
        """Insert an invoice; returns its id, or None if the same file already exists."""
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO invoices
               (message_id, sender, subject, received_at, filename, file_path, sha256,
                vendor, invoice_number, invoice_date, amount, currency)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                inv.message_id, inv.sender, inv.subject, inv.received_at, inv.filename,
                inv.file_path, inv.sha256, inv.vendor, inv.invoice_number,
                inv.invoice_date.isoformat() if inv.invoice_date else None,
                inv.amount, inv.currency,
            ),
        )
        self.conn.commit()
        return cur.lastrowid if cur.rowcount else None

    def get(self, invoice_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()

    def list(
        self,
        *,
        status: str | None = None,
        vendor: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[sqlite3.Row]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if vendor:
            clauses.append("vendor LIKE ?")
            params.append(f"%{vendor}%")
        # Filter on invoice date, falling back to the email date.
        if since:
            clauses.append("COALESCE(invoice_date, substr(received_at, 1, 10)) >= ?")
            params.append(since)
        if until:
            clauses.append("COALESCE(invoice_date, substr(received_at, 1, 10)) <= ?")
            params.append(until)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM invoices {where} ORDER BY COALESCE(invoice_date, received_at) DESC, id DESC"
        return self.conn.execute(sql, params).fetchall()

    def update(self, invoice_id: int, **fields) -> bool:
        unknown = set(fields) - EDITABLE
        if unknown:
            raise ValueError(f"Not editable: {', '.join(sorted(unknown))}")
        if not fields:
            return False
        sets = ", ".join(f"{k} = ?" for k in fields)
        cur = self.conn.execute(f"UPDATE invoices SET {sets} WHERE id = ?", (*fields.values(), invoice_id))
        self.conn.commit()
        return cur.rowcount > 0

    def totals(self, *, status: str | None = None) -> list[sqlite3.Row]:
        """Sum of amounts per month and currency."""
        where, params = "", []
        if status:
            where, params = "WHERE status = ?", [status]
        return self.conn.execute(
            f"""SELECT substr(COALESCE(invoice_date, received_at), 1, 7) AS month,
                       COALESCE(currency, '?') AS currency,
                       COUNT(*) AS count,
                       ROUND(SUM(COALESCE(amount, 0)), 2) AS total,
                       SUM(amount IS NULL) AS missing_amount
                FROM invoices {where}
                GROUP BY month, currency
                ORDER BY month DESC, currency""",
            params,
        ).fetchall()
