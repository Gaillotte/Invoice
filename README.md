# Invoice

Collect, organise and track the invoices you receive by email in your Gmail account.

`invoices fetch` searches Gmail for invoice emails, downloads their attachments (PDF, images,
XML e-invoices), reads the vendor, invoice number, date and amount where it can, files them by
date, and records them in a local SQLite register. You can then list, correct, mark as paid,
summarise and export them to CSV.

Everything stays on your machine. The tool can read your mail and add a label; it never
deletes or sends anything.

## Setup

1. **Install** (Python 3.11+):

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. **Create Gmail API credentials** (one-time):
   - In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable the **Gmail API**.
   - Under *APIs & Services → OAuth consent screen*, choose **External** and add your own Gmail
     address as a **test user**.
   - Under *Credentials → Create credentials → OAuth client ID*, pick **Desktop app** and download
     the JSON file as `credentials.json` in this folder.

3. **Configure**: `cp config.example.toml config.toml` and edit it. The main settings are the
   Gmail account and the keywords used to find invoice emails:

   ```toml
   account = "you@gmail.com"
   keywords = ["Facture", "Facturation", "Invoice"]
   invoices_dir = "~/Documents/Factures"
   ```

   `invoices_dir` is where invoice files are saved, in `YYYY/MM` sub-folders (default:
   `data/files`). The register itself (`invoices.db`) stays in `data_dir`.

   `account` is pre-selected when you sign in, and the tool refuses to run if the saved token
   belongs to a different mailbox. There is no password setting: Google rejects plain
   passwords for programs using the Gmail API, so access goes through Google sign-in below.

   An email is selected when its **subject** or an **attachment's file name** contains any of
   these words (case-insensitive, whole words — Gmail treats `Facture` and `Facturation` as
   different words, so list each form you want). Phrases like `"Avis de paiement"` work too.
   Run `invoices query` to see the resulting Gmail search, and paste it into Gmail to check
   which emails it matches. You can also set the time range, label and storage folder.

4. **Authorise**: `invoices auth` opens a browser to sign in; the token is saved to `token.json`.

`credentials.json`, `token.json`, `config.toml` and `data/` are git-ignored. Don't commit them.

## Usage

```bash
invoices fetch --dry-run          # preview what would be imported
invoices fetch                    # import new invoices
invoices list --status unpaid     # what's left to pay
invoices show 12                  # every field of invoice #12
invoices query                    # show the keywords and the Gmail search used
invoices edit 12 --amount 89.90 --currency EUR --vendor "EDF"
invoices pay 12 13 --on 2026-11-05
invoices summary                  # totals per month and currency
invoices export -o 2026.csv --since 2026-01-01
```

Other options: `fetch -k Facture -k Avoir` to use other keywords for one run,
`fetch --query '...'` to replace the whole search, `fetch --newer-than 30d`,
`fetch --limit 20`, `fetch --reprocess` to look at already-processed emails again,
`ignore <id>` for false positives, `-c other.toml` to use another config file.

## How it works

| Step | Detail |
| --- | --- |
| Search | Emails with an attachment whose subject or attachment file name contains one of the configured `keywords` (default: Facture, Facturation, Invoice), newer than 1 year. `extra_query` adds Gmail terms; `query` replaces the generated search entirely. |
| Download | Attachments with the configured extensions are saved to `<invoices_dir>/YYYY/MM/<date>_<vendor>_<filename>`. Identical files (same SHA-256) are stored only once. |
| Extract | Text from PDFs (or the email body as a fallback) is scanned for the amount due (`Amount due`, `Total TTC`, `Net à payer`, …), currency, invoice number and date, in English and French. The vendor comes from the sender's name. Scanned (image-only) PDFs have no text, so fill those in with `invoices edit`. |
| Record | Each invoice is a row in `data/invoices.db` with status `unpaid`, `paid` or `ignored`. |
| Mark | Processed emails get the Gmail label `invoices-processed` and are excluded from later searches. |

## Development

```bash
pytest
```

Tests use a fake Gmail source, so they need no network access or credentials.

Layout: `src/invoice_manager/` — `gmail.py` (API access), `fetcher.py` (import pipeline),
`extract.py` (field extraction), `store.py` (SQLite register), `cli.py` (commands).
