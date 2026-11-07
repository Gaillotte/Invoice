"""Pull invoice attachments out of Gmail into the local register."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .config import Config
from .extract import extract_fields, pdf_text
from .gmail import Attachment, Message
from .store import NewInvoice, Store


class MailSource(Protocol):
    def search(self, query: str, limit: int | None = None): ...
    def get_message(self, message_id: str) -> Message: ...
    def get_attachment(self, message_id: str, att: Attachment) -> bytes: ...
    def add_label(self, message_id: str, name: str) -> None: ...


@dataclass
class FetchReport:
    messages_seen: int = 0
    messages_skipped: int = 0
    invoices_added: list[int] = field(default_factory=list)
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)


def safe_name(s: str, max_len: int = 60) -> str:
    s = re.sub(r"[^\w.\-]+", "_", s, flags=re.UNICODE).strip("._")
    return s[:max_len] or "unknown"


def fetch(
    source: MailSource,
    store: Store,
    cfg: Config,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    reprocess: bool = False,
    log=print,
) -> FetchReport:
    report = FetchReport()
    query = cfg.full_query()
    log(f"Searching Gmail: {query}")

    for message_id in source.search(query, limit=limit):
        report.messages_seen += 1
        if not reprocess and store.is_processed(message_id):
            report.messages_skipped += 1
            continue
        try:
            msg = source.get_message(message_id)
            kept = [a for a in msg.attachments if Path(a.filename).suffix.lower() in cfg.extensions]
            if not kept:
                log(f"  - {msg.subject!r}: no matching attachment")
            for att in kept:
                _handle_attachment(source, store, cfg, msg, att, report, dry_run, log)
            if not dry_run:
                store.mark_processed(message_id)
                if cfg.processed_label:
                    source.add_label(message_id, cfg.processed_label)
        except Exception as exc:  # keep going; report at the end
            report.errors.append(f"{message_id}: {exc}")
            log(f"  ! {message_id}: {exc}")
    return report


def _handle_attachment(source, store, cfg, msg, att, report, dry_run, log) -> None:
    data = source.get_attachment(msg.id, att)
    digest = hashlib.sha256(data).hexdigest()
    if store.has_file(digest):
        report.duplicates += 1
        log(f"  = {att.filename}: already in register")
        return

    text = pdf_text(data) if att.filename.lower().endswith(".pdf") else ""
    if att.filename.lower().endswith(".xml"):  # e-invoices (Factur-X / UBL) are plain XML
        text = data.decode("utf-8", "replace")
    fields = extract_fields(sender=msg.sender, subject=msg.subject, body=msg.body_text, attachment_text=text)

    when = fields.invoice_date or msg.received_at.date()
    rel = Path(f"{when:%Y}") / f"{when:%m}" / (
        f"{when:%Y-%m-%d}_{safe_name(fields.vendor or 'unknown', 40)}_{safe_name(att.filename)}"
    )
    dest = cfg.files_dir / rel
    amount = f"{fields.amount:.2f} {fields.currency or ''}".strip() if fields.amount is not None else "amount ?"
    log(f"  + {fields.vendor or '?'} | {when} | {amount} | {att.filename}")
    if dry_run:
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():  # same name, different content
        dest = dest.with_name(f"{dest.stem}_{digest[:8]}{dest.suffix}")
    dest.write_bytes(data)

    new_id = store.add(
        NewInvoice(
            message_id=msg.id,
            sender=msg.sender,
            subject=msg.subject,
            received_at=msg.received_at.isoformat(timespec="seconds"),
            filename=att.filename,
            file_path=str(dest),
            sha256=digest,
            vendor=fields.vendor,
            invoice_number=fields.invoice_number,
            invoice_date=fields.invoice_date,
            amount=fields.amount,
            currency=fields.currency,
        )
    )
    if new_id:
        report.invoices_added.append(new_id)
