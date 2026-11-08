import base64
from datetime import datetime, timezone

from invoice_manager.config import Config
from invoice_manager.fetcher import fetch
from invoice_manager.gmail import Attachment, Message, parse_message
from invoice_manager.store import Store


class FakeSource:
    def __init__(self, messages: dict[str, tuple[Message, dict[str, bytes]]]):
        self.messages = messages
        self.labelled: list[tuple[str, str]] = []

    def search(self, query, limit=None):
        ids = list(self.messages)
        return iter(ids[:limit] if limit else ids)

    def get_message(self, message_id):
        return self.messages[message_id][0]

    def get_attachment(self, message_id, att):
        return self.messages[message_id][1][att.filename]

    def add_label(self, message_id, name):
        self.labelled.append((message_id, name))


def _msg(mid, files, body="Total TTC : 120,00 €"):
    return (
        Message(
            id=mid,
            sender="Acme <billing@acme.com>",
            subject=f"Facture n° F-{mid}1",
            received_at=datetime(2024, 3, 5, 10, tzinfo=timezone.utc),
            body_text=body,
            attachments=[Attachment(n, "application/octet-stream", "x", None) for n in files],
        ),
        files,
    )


def test_fetch_saves_and_dedupes(tmp_path):
    cfg = Config(data_dir=tmp_path)
    store = Store(cfg.db_path)
    src = FakeSource(
        {
            "m1": _msg("m1", {"inv.xml": b"<x>Total: 120,00 EUR</x>", "logo.gif": b"gif"}),
            "m2": _msg("m2", {"copy.xml": b"<x>Total: 120,00 EUR</x>"}),  # same bytes
        }
    )
    report = fetch(src, store, cfg, log=lambda *_: None)

    assert len(report.invoices_added) == 1
    assert report.duplicates == 1
    row = store.list()[0]
    assert row["vendor"] == "Acme"
    assert row["amount"] == 120.0
    assert row["currency"] == "EUR"
    assert row["invoice_number"] == "F-m11"
    assert (tmp_path / "files" / "2024" / "03").exists()
    assert src.labelled == [("m1", "invoices-processed"), ("m2", "invoices-processed")]

    # Second run skips processed messages.
    report2 = fetch(src, store, cfg, log=lambda *_: None)
    assert report2.messages_skipped == 2 and not report2.invoices_added


def test_dry_run_saves_nothing(tmp_path):
    cfg = Config(data_dir=tmp_path)
    store = Store(cfg.db_path)
    src = FakeSource({"m1": _msg("m1", {"inv.pdf": b"not really a pdf"})})
    fetch(src, store, cfg, dry_run=True, log=lambda *_: None)
    assert store.list() == []
    assert not store.is_processed("m1")
    assert src.labelled == []


def test_status_and_totals(tmp_path):
    cfg = Config(data_dir=tmp_path)
    store = Store(cfg.db_path)
    fetch(FakeSource({"m1": _msg("m1", {"a.xml": b"Total 10,00 EUR"})}), store, cfg, log=lambda *_: None)
    inv_id = store.list()[0]["id"]
    store.update(inv_id, status="paid", paid_on="2024-04-01")
    assert store.list(status="paid")[0]["paid_on"] == "2024-04-01"
    assert store.list(status="unpaid") == []
    t = store.totals()[0]
    assert (t["month"], t["currency"], t["count"], t["total"]) == ("2024-03", "EUR", 1, 10.0)


def test_parse_gmail_message():
    b64 = lambda s: base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")
    raw = {
        "id": "abc",
        "internalDate": "1709632800000",
        "payload": {
            "headers": [{"name": "From", "value": "X <x@y.z>"}, {"name": "Subject", "value": "Invoice"}],
            "mimeType": "multipart/mixed",
            "parts": [
                {"mimeType": "text/html", "body": {"data": b64("<p>Total&nbsp;<b>5 €</b></p>")}},
                {"mimeType": "application/pdf", "filename": "f.pdf", "body": {"attachmentId": "att1"}},
            ],
        },
    }
    msg = parse_message(raw)
    assert msg.subject == "Invoice"
    assert "Total 5 €" in msg.body_text
    assert msg.attachments[0].filename == "f.pdf"
    assert msg.attachments[0].attachment_id == "att1"


def test_fetch_body_keyword_and_skip_non_matching(tmp_path):
    cfg = Config(data_dir=tmp_path)
    store = Store(cfg.db_path)
    body_hit = _msg("m1", {"doc.xml": b"Total 10,00 EUR"}, body="Ci-joint votre facture.")
    body_hit[0].subject = "Votre commande"
    sender_only = _msg("m2", {"doc2.xml": b"Total 5,00 EUR"}, body="Merci")
    sender_only[0].subject = "Votre commande"  # only the sender address says 'factures'
    sender_only[0].sender = "factures@shop.fr"
    src = FakeSource({"m1": body_hit, "m2": sender_only})

    report = fetch(src, store, cfg, log=lambda *_: None)
    assert len(report.invoices_added) == 1 and report.not_matching == 1
    assert not store.is_processed("m2")  # re-checked next time, e.g. after keywords change
    assert ("m2", "invoices-processed") not in src.labelled

    cfg.search_in = ["subject", "filename"]
    report = fetch(src, store, cfg, reprocess=True, log=lambda *_: None)
    assert report.not_matching == 2
