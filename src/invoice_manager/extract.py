"""Best-effort extraction of invoice fields from attachment text and email metadata.

Heuristics cover common English and French layouts. Anything not found is left
as ``None`` so it can be filled in by hand with ``invoices edit``.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parseaddr

CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP", "CHF": "CHF"}
CURRENCY_CODES = {"EUR", "USD", "GBP", "CHF", "CAD", "AUD", "JPY"}

# A number such as 1,234.56 / 1 234,56 / 1.234,56 / 1234.5 / 99
_NUM = r"\d{1,3}(?:[   .,']\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_CUR = r"€|\$|£|EUR|USD|GBP|CHF|CAD|AUD|JPY"

# Labels that usually precede the amount actually due, strongest first.
_TOTAL_LABELS = [
    r"amount\s+due",
    r"total\s+due",
    r"balance\s+due",
    r"net\s+[àa]\s+payer",
    r"montant\s+(?:total\s+)?(?:ttc|d[ûu]|[àa]\s+payer)",
    r"total\s+ttc",
    r"grand\s+total",
    r"total\s+(?:amount|incl\.?\s*(?:vat|tax))",
    r"total",
]

_INVOICE_NO = re.compile(
    r"\b(?:invoice|facture|bill|receipt|re[çc]u)\s*(?:(?:n(?:o|um(?:ber|[ée]ro)?)?\.?|#|n°|nº)\s*[:#]?\s*)?"
    r"([A-Z0-9][A-Z0-9\-_/\.]{2,30})",
    re.IGNORECASE,
)

_DATE_LABEL = re.compile(
    r"(?:invoice\s+date|date\s+(?:de\s+(?:la\s+)?)?facture|date\s+d'[ée]mission|"
    r"issue\s+date|date)\s*[:\-]?\s*([0-9]{1,4}[./\-][0-9]{1,2}[./\-][0-9]{1,4}|"
    r"\d{1,2}\s+[A-Za-zéûè]+\.?\s+\d{4}|[A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE,
)

_MONTHS = {
    "jan": 1, "janv": 1, "janvier": 1, "january": 1,
    "feb": 2, "fév": 2, "fev": 2, "févr": 2, "fevr": 2, "février": 2, "fevrier": 2, "february": 2,
    "mar": 3, "mars": 3, "march": 3,
    "apr": 4, "avr": 4, "avril": 4, "april": 4,
    "may": 5, "mai": 5,
    "jun": 6, "juin": 6, "june": 6,
    "jul": 7, "juil": 7, "juillet": 7, "july": 7,
    "aug": 8, "août": 8, "aout": 8, "august": 8,
    "sep": 9, "sept": 9, "septembre": 9, "september": 9,
    "oct": 10, "octobre": 10, "october": 10,
    "nov": 11, "novembre": 11, "november": 11,
    "dec": 12, "déc": 12, "décembre": 12, "decembre": 12, "december": 12,
}


@dataclass
class InvoiceFields:
    vendor: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    amount: float | None = None
    currency: str | None = None


def pdf_text(data: bytes, max_pages: int = 5) -> str:
    """Return the text of the first pages of a PDF ('' if it cannot be read)."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:max_pages])
    except Exception:  # corrupt, encrypted or scanned PDFs
        return ""


def parse_amount(raw: str) -> float | None:
    """Parse a localised number: '1 234,56', '1.234,56', '1,234.56', '12.5'."""
    s = re.sub(r"[   ']", "", raw.strip())
    if not s:
        return None
    if "," in s and "." in s:
        # The right-most separator is the decimal one.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head.replace(',', '')}.{tail}" if len(tail) <= 2 else s.replace(",", "")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.rpartition(".")[2]) == 3):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _normalise_currency(token: str | None) -> str | None:
    if not token:
        return None
    token = token.strip().upper()
    return CURRENCY_SYMBOLS.get(token, token if token in CURRENCY_CODES else None)


def find_total(text: str) -> tuple[float | None, str | None]:
    """Find the amount due and its currency."""
    for label in _TOTAL_LABELS:
        pattern = re.compile(
            rf"{label}[^\n\d€$£]{{0,40}}?(?P<c1>{_CUR})?\s*(?P<n>{_NUM})\s*(?P<c2>{_CUR})?",
            re.IGNORECASE,
        )
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        # For the generic "total" label, the last occurrence is usually the final total.
        m = matches[-1] if label == "total" else matches[0]
        amount = parse_amount(m.group("n"))
        if amount is not None:
            currency = _normalise_currency(m.group("c1") or m.group("c2"))
            return amount, currency or guess_currency(text)
    return None, guess_currency(text)


def guess_currency(text: str) -> str | None:
    counts = {code: 0 for code in CURRENCY_CODES}
    for sym, code in CURRENCY_SYMBOLS.items():
        counts[code] += text.count(sym)
    for code in CURRENCY_CODES:
        counts[code] += len(re.findall(rf"\b{code}\b", text))
    best = max(counts, key=counts.get)
    return best if counts[best] else None


def parse_date(raw: str) -> date | None:
    raw = raw.strip().rstrip(".,")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    m = re.match(r"(\d{1,2})\s+([A-Za-zéûè]+)\.?\s+(\d{4})", raw)
    if m and m.group(2).lower() in _MONTHS:
        try:
            return date(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            return None
    m = re.match(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})", raw)
    if m and m.group(1).lower() in _MONTHS:
        try:
            return date(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
        except ValueError:
            return None
    return None


def find_invoice_date(text: str) -> date | None:
    for m in _DATE_LABEL.finditer(text):
        d = parse_date(m.group(1))
        if d:
            return d
    return None


def find_invoice_number(*texts: str) -> str | None:
    for text in texts:
        if not text:
            continue
        for m in _INVOICE_NO.finditer(text):
            if any(ch.isdigit() for ch in m.group(1)):
                return m.group(1).rstrip(".")
    return None


def vendor_from_sender(sender: str) -> str | None:
    """'Acme Billing <billing@acme.com>' -> 'Acme Billing'; bare address -> 'acme.com'."""
    name, addr = parseaddr(sender)
    name = name.strip().strip('"')
    if name:
        return name
    if "@" in addr:
        domain = addr.split("@", 1)[1].lower()
        parts = domain.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else domain
    return None


def extract_fields(*, sender: str, subject: str, body: str, attachment_text: str) -> InvoiceFields:
    """Combine attachment text (preferred) and email text into invoice fields."""
    primary = attachment_text or ""
    fallback = f"{subject}\n{body}"

    amount, currency = find_total(primary)
    if amount is None:
        amount, currency = find_total(fallback)

    return InvoiceFields(
        vendor=vendor_from_sender(sender),
        invoice_number=find_invoice_number(primary, subject, body),
        invoice_date=find_invoice_date(primary) or find_invoice_date(fallback),
        amount=amount,
        currency=currency,
    )
