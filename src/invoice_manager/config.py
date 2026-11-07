"""Configuration loading."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_QUERY = (
    'has:attachment (subject:(invoice OR facture OR bill OR receipt OR "order confirmation") '
    "OR filename:(invoice OR facture)) -label:invoices-processed"
)


@dataclass
class Config:
    query: str = DEFAULT_QUERY
    newer_than: str = "1y"
    processed_label: str = "invoices-processed"
    data_dir: Path = Path("data")
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
        return self.data_dir / "files"

    def full_query(self) -> str:
        q = self.query
        if self.newer_than:
            q += f" newer_than:{self.newer_than}"
        return q


def load_config(path: Path | None = None) -> Config:
    """Load config from a TOML file; missing file or keys fall back to defaults."""
    path = path or Path("config.toml")
    if not path.exists():
        return Config()
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    cfg = Config()
    for key, value in raw.items():
        if not hasattr(cfg, key):
            raise ValueError(f"Unknown config key: {key!r}")
        if key in {"data_dir", "credentials_file", "token_file"}:
            value = Path(value)
        if key == "extensions":
            value = [e.lower() if e.startswith(".") else f".{e.lower()}" for e in value]
        setattr(cfg, key, value)
    return cfg
