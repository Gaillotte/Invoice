from datetime import date

import pytest

from invoice_manager.extract import (
    extract_fields,
    find_invoice_date,
    find_invoice_number,
    find_total,
    parse_amount,
    vendor_from_sender,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1,234.56", 1234.56),
        ("1 234,56", 1234.56),
        ("1.234,56", 1234.56),
        ("1234.5", 1234.5),
        ("99", 99.0),
        ("12,50", 12.5),
        ("1,234", 1234.0),
        ("1.234", 1234.0),
        ("1 234,00", 1234.0),
    ],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_total_english():
    text = "Subtotal $100.00\nTax $20.00\nAmount due: $120.00"
    assert find_total(text) == (120.0, "USD")


def test_total_french():
    text = "Total HT 100,00 €\nTVA 20,00 €\nTotal TTC : 120,00 €"
    assert find_total(text) == (120.0, "EUR")


def test_total_net_a_payer_beats_generic_total():
    text = "Total HT 50,00\nNet à payer 60,00 EUR\nTotal articles 3"
    assert find_total(text) == (60.0, "EUR")


def test_total_missing():
    assert find_total("Hello, thanks for your order") == (None, None)


def test_invoice_number():
    assert find_invoice_number("Invoice No: INV-2024-0042") == "INV-2024-0042"
    assert find_invoice_number("Facture n° F2024/118") == "F2024/118"
    assert find_invoice_number("Invoice #A12345") == "A12345"
    assert find_invoice_number("Your invoice is attached") is None


def test_invoice_date():
    assert find_invoice_date("Invoice date: 2024-03-05") == date(2024, 3, 5)
    assert find_invoice_date("Date de facture : 05/03/2024") == date(2024, 3, 5)
    assert find_invoice_date("Date: 5 mars 2024") == date(2024, 3, 5)
    assert find_invoice_date("Issue date March 5, 2024") == date(2024, 3, 5)


def test_vendor_from_sender():
    assert vendor_from_sender('"Acme Billing" <billing@acme.com>') == "Acme Billing"
    assert vendor_from_sender("noreply@mail.edf.fr") == "edf.fr"


def test_extract_falls_back_to_email_body():
    fields = extract_fields(
        sender="Shop <shop@example.com>",
        subject="Your invoice INV-77",
        body="Total: 45,90 €",
        attachment_text="",
    )
    assert fields.vendor == "Shop"
    assert fields.invoice_number == "INV-77"
    assert fields.amount == 45.9
    assert fields.currency == "EUR"
