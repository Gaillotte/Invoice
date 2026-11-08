"""Local check that an email really contains a keyword where the config says to look.

Gmail search is broader than we want (a bare word also matches the sender, for
example), so every email Gmail returns is checked again here.
"""

from __future__ import annotations

import re
import unicodedata

from .gmail import Message


def _fold(text: str) -> str:
    """Lower-case and strip accents, so 'FACTURÉ' and 'facture' compare equal."""
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _pattern(keyword: str) -> re.Pattern:
    # Whole word: not preceded/followed by a letter or digit. "_", "-", "." and spaces
    # count as separators, so "Facture" matches "Facture_2026.pdf" but not "Factures".
    words = [re.escape(w) for w in _fold(keyword).split()]
    return re.compile(r"(?<![^\W_])" + r"\s+".join(words) + r"(?![^\W_])")


def matched_places(msg: Message, keywords: list[str], search_in: list[str]) -> list[str]:
    """Return 'keyword in place' strings for every hit; empty list = no match."""
    texts = {
        "subject": msg.subject,
        "filename": " ".join(a.filename for a in msg.attachments),
        "body": msg.body_text,
    }
    hits = []
    for place in search_in:
        folded = _fold(texts.get(place, "") or "")
        for kw in keywords:
            if kw.strip() and _pattern(kw).search(folded):
                hits.append(f"{kw} in {place}")
    return hits
