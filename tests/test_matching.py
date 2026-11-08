from datetime import datetime, timezone

import pytest

from invoice_manager.gmail import Attachment, Message
from invoice_manager.matching import matched_places

ALL = ["subject", "filename", "body"]
KW = ["Facture", "Facturation", "Invoice", "Avis de paiement"]


def msg(subject="", files=(), body="", sender="Shop <factures@shop.fr>"):
    return Message("id", sender, subject, datetime(2026, 11, 1, tzinfo=timezone.utc), body,
                   [Attachment(f, "application/pdf", "a", None) for f in files])


@pytest.mark.parametrize("m, expected", [
    (msg(subject="Votre FACTURE d'octobre"), ["Facture in subject"]),
    (msg(files=["edf-facture_2026.10.pdf"]), ["Facture in filename"]),
    (msg(body="Veuillez trouver ci-joint votre facture."), ["Facture in body"]),
    (msg(body="Avis   de\npaiement"), ["Avis de paiement in body"]),
    (msg(subject="Facturé le 3 novembre"), ["Facture in subject"]),  # accent-insensitive
])
def test_places(m, expected):
    assert matched_places(m, KW, ALL) == expected


def test_whole_words_only():
    assert matched_places(msg(subject="Vos factures", files=["MaFacture1.pdf"]), KW, ALL) == []


def test_sender_is_not_searched():
    assert matched_places(msg(subject="Commande", body="Merci"), KW, ALL) == []


def test_respects_search_in():
    m = msg(subject="Commande", body="votre facture")
    assert matched_places(m, KW, ["subject", "filename"]) == []
    assert matched_places(m, KW, ["body"]) == ["Facture in body"]
