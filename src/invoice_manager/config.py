"""Configuration loading."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_KEYWORDS = ["Facture", "Facturation", "Invoice"]


def _gmail_term(word: str) -> str:
    """Quote a keyword for Gmail search if it contains spaces or special characters."""
    word = word.replace('"', "").strip()
    return f'"{word}"' if any(c in word for c in " ()-{}:") else word


@dataclass
class Config:
    # Gmail address to manage. Used to pre-select it at sign-in and to refuse a token
    # that belongs to another mailbox. Empty = whichever account you sign in with.
    account: str = ""
    # Words searched (case-insensitive) in the subject and attachment file names.
    keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    # Only keep emails that have an attachment.
    require_attachment: bool = True
    # Extra Gmail search terms appended to the generated query, e.g. "-from:newsletter@x.com".
    extra_query: str = ""
    # Full Gmail query; when set, replaces the query generated from keywords.
    query: str = ""
    newer_than: str = "1y"
    processed_label: str = "invoices-processed"
    data_dir: Path = Path("data")
    # Folder where invoice files are saved (in YYYY/MM sub-folders). Empty = <data_dir>/files.
    invoices_dir: Path | None = None
    extensions: list[str] = field(
        default_factory=lambda: [".pdf", ".png", ".jpg", ".jpeg", ".xml"]
    )
    credentials_file: Path = Path("credentials.json")
    token_file: Path = Path("token.json")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "invoices.db"

    @property
    def files_dir(self) -> Path:
        return self.invoices_dir or self.data_dir / "files"

    def keyword_query(self) -> str:
        """Gmail query matching any keyword in the subject or an attachment's file name."""
        words = [_gmail_term(k) for k in self.keywords if k.strip()]
        if not words:
            raise ValueError("No keywords configured: set 'keywords' (or 'query') in the config file.")
        terms = [f"subject:{w}" for w in words] + [f"filename:{w}" for w in words]
        parts = []
        if self.require_attachment:
            parts.append("has:attachment")
        parts.append("{" + " ".join(terms) + "}")  # {a b c} means a OR b OR c in Gmail
        if self.extra_query:
            parts.append(self.extra_query)
        return " ".join(parts)

    def full_query(self) -> str:
        q = self.query or self.keyword_query()
        if self.processed_label:
            q += f" -label:{self.processed_label}"
        if self.newer_than:
            q += f" newer_than:{self.newer_than}"
        return q


# Keys refused on purpose: Google rejects plain passwords for Gmail API access.
_FORBIDDEN = {
    "password": "Gmail does not accept a password here. Access uses Google sign-in "
    "('invoices auth'), which stores a revocable token in token.json — see README.",
}

_PATHS = {"data_dir", "invoices_dir", "credentials_file", "token_file"}


def load_config(path: Path | None = None) -> Config:
    """Load config from a TOML file; missing file or keys fall back to defaults."""
    path = path or Path("config.toml")
    if not path.exists():
        return Config()
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    cfg = Config()
    for key, value in raw.items():
        if key in _FORBIDDEN:
            raise ValueError(f"{path}: '{key}' is not supported. {_FORBIDDEN[key]}")
        if not hasattr(cfg, key):
            raise ValueError(f"Unknown config key in {path}: {key!r}")
        if key in _PATHS:
            # "~" is expanded; an empty invoices_dir means the default location.
            value = Path(value).expanduser() if value else (None if key == "invoices_dir" else Path("."))
        elif key == "extensions":
            value = [e.lower() if e.startswith(".") else f".{e.lower()}" for e in value]
        elif key == "keywords":
            if isinstance(value, str) or not all(isinstance(k, str) for k in value):
                raise ValueError(f"'keywords' in {path} must be a list of strings")
        setattr(cfg, key, value)
    return cfg
