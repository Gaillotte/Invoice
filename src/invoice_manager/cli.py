"""Command-line interface: ``invoices <command>``."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from .config import load_config
from .store import COLUMNS, Store


def _store(cfg) -> Store:
    return Store(cfg.db_path)


def _gmail(cfg):
    from .gmail import GmailClient, authenticate, check_account

    client = GmailClient(authenticate(cfg.credentials_file, cfg.token_file, cfg.account or None))
    if cfg.account:
        check_account(client.email_address(), cfg.account, cfg.token_file)
    return client


def _iso_date(value: str) -> str:
    """argparse type: accept only YYYY-MM-DD dates."""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}, expected YYYY-MM-DD")


def _fmt_amount(row) -> str:
    if row["amount"] is None:
        return "?"
    return f"{row['amount']:,.2f} {row['currency'] or ''}".strip()


def _print_table(rows) -> None:
    if not rows:
        print("No invoices.")
        return
    header = ("ID", "Date", "Vendor", "Number", "Amount", "Status")
    data = [
        (
            str(r["id"]),
            r["invoice_date"] or (r["received_at"] or "")[:10],
            (r["vendor"] or "?")[:30],
            (r["invoice_number"] or "")[:20],
            _fmt_amount(r),
            r["status"],
        )
        for r in rows
    ]
    widths = [max(len(h), *(len(d[i]) for d in data)) for i, h in enumerate(header)]
    line = "  ".join(h.ljust(w) for h, w in zip(header, widths))
    print(line.rstrip())
    print("-" * len(line.rstrip()))
    for d in data:
        print("  ".join(v.rjust(w) if i == 4 else v.ljust(w) for i, (v, w) in enumerate(zip(d, widths))).rstrip())


# -- commands ---------------------------------------------------------------

def cmd_auth(cfg, args) -> int:
    client = _gmail(cfg)
    print(f"Authorised as {client.email_address()}. Token saved to {cfg.token_file}")
    return 0


def cmd_fetch(cfg, args) -> int:
    from .fetcher import fetch

    if args.keyword:
        cfg.keywords, cfg.query = args.keyword, ""
    if args.query:
        cfg.query = args.query
    if args.newer_than is not None:
        cfg.newer_than = args.newer_than
    store = _store(cfg)
    try:
        report = fetch(
            _gmail(cfg), store, cfg, limit=args.limit, dry_run=args.dry_run, reprocess=args.reprocess
        )
    finally:
        store.close()
    print(
        f"\n{report.messages_seen} message(s) matched, {report.messages_skipped} already processed, "
        f"{len(report.invoices_added)} invoice(s) added, {report.duplicates} duplicate(s), "
        f"{len(report.errors)} error(s)."
        + (" (dry run — nothing saved)" if args.dry_run else "")
    )
    return 1 if report.errors else 0


def cmd_query(cfg, args) -> int:
    print(f"Account: {cfg.account or '(any — whichever account you sign in with)'}")
    print(f"Invoices folder: {cfg.files_dir}")
    print("Keywords: " + ", ".join(cfg.keywords) + ("  (ignored: 'query' is set)" if cfg.query else ""))
    print(f"Gmail query: {cfg.full_query()}")
    print("Tip: paste the query into the Gmail search box to see which emails it matches.")
    return 0


def cmd_list(cfg, args) -> int:
    store = _store(cfg)
    rows = store.list(status=args.status, vendor=args.vendor, since=args.since, until=args.until)
    _print_table(rows)
    store.close()
    return 0


def cmd_show(cfg, args) -> int:
    store = _store(cfg)
    row = store.get(args.id)
    store.close()
    if not row:
        print(f"No invoice #{args.id}", file=sys.stderr)
        return 1
    for col in COLUMNS:
        print(f"{col:>15}: {row[col] if row[col] is not None else ''}")
    return 0


def cmd_edit(cfg, args) -> int:
    fields = {
        k: v
        for k, v in {
            "vendor": args.vendor,
            "invoice_number": args.number,
            "invoice_date": args.date,
            "amount": args.amount,
            "currency": args.currency.upper() if args.currency else None,
            "notes": args.notes,
        }.items()
        if v is not None
    }
    if not fields:
        print("Nothing to change.", file=sys.stderr)
        return 1
    store = _store(cfg)
    ok = store.update(args.id, **fields)
    store.close()
    print(f"Updated #{args.id}" if ok else f"No invoice #{args.id}")
    return 0 if ok else 1


def _set_status(cfg, ids, status, paid_on=None) -> int:
    store = _store(cfg)
    missing = [i for i in ids if not store.update(i, status=status, paid_on=paid_on)]
    store.close()
    for i in missing:
        print(f"No invoice #{i}", file=sys.stderr)
    done = len(ids) - len(missing)
    print(f"{done} invoice(s) marked {status}.")
    return 1 if missing else 0


def cmd_pay(cfg, args) -> int:
    return _set_status(cfg, args.ids, "paid", args.on or date.today().isoformat())


def cmd_unpay(cfg, args) -> int:
    return _set_status(cfg, args.ids, "unpaid", None)


def cmd_ignore(cfg, args) -> int:
    return _set_status(cfg, args.ids, "ignored", None)


def cmd_summary(cfg, args) -> int:
    store = _store(cfg)
    rows = store.totals(status=args.status)
    store.close()
    if not rows:
        print("No invoices.")
        return 0
    print(f"{'Month':<8}  {'Cur':<4}  {'Count':>5}  {'Total':>12}  Missing amount")
    for r in rows:
        print(
            f"{r['month'] or '?':<8}  {r['currency']:<4}  {r['count']:>5}  {r['total']:>12,.2f}  "
            f"{r['missing_amount'] or ''}"
        )
    return 0


def cmd_export(cfg, args) -> int:
    store = _store(cfg)
    rows = store.list(status=args.status, vendor=args.vendor, since=args.since, until=args.until)
    store.close()
    # --excel: semicolon separator, decimal comma and a UTF-8 BOM, as expected by
    # Excel in French (and most European) locales.
    encoding = "utf-8-sig" if args.excel else "utf-8"
    out = open(args.output, "w", newline="", encoding=encoding) if args.output != "-" else sys.stdout
    try:
        writer = csv.writer(out, delimiter=";" if args.excel else ",")
        writer.writerow(COLUMNS)
        for r in rows:
            values = [r[c] for c in COLUMNS]
            if args.excel and r["amount"] is not None:
                values[COLUMNS.index("amount")] = f"{r['amount']:.2f}".replace(".", ",")
            writer.writerow(values)
    finally:
        if out is not sys.stdout:
            out.close()
    if args.output != "-":
        print(f"Exported {len(rows)} invoice(s) to {args.output}")
    return 0


# -- parser -----------------------------------------------------------------

def _add_filters(p) -> None:
    p.add_argument("--status", choices=["unpaid", "paid", "ignored"])
    p.add_argument("--vendor", help="substring match on vendor")
    p.add_argument("--since", type=_iso_date, help="YYYY-MM-DD")
    p.add_argument("--until", type=_iso_date, help="YYYY-MM-DD")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="invoices", description="Manage invoices received in Gmail.")
    p.add_argument("-c", "--config", type=Path, default=Path("config.toml"), help="config file (default: config.toml)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="authorise access to your Gmail account").set_defaults(func=cmd_auth)

    f = sub.add_parser("fetch", help="download new invoices from Gmail")
    f.add_argument("--limit", type=int, help="max messages to look at")
    f.add_argument("-k", "--keyword", action="append", help="use this keyword instead of the configured ones (repeatable)")
    f.add_argument("--query", help="override the whole Gmail search query")
    f.add_argument("--newer-than", help="override newer_than, e.g. 30d, 6m, 2y ('' = no limit)")
    f.add_argument("--dry-run", action="store_true", help="show what would be added, save nothing")
    f.add_argument("--reprocess", action="store_true", help="also look at messages already processed")
    f.set_defaults(func=cmd_fetch)

    sub.add_parser("query", help="show the keywords and the Gmail query that fetch will use").set_defaults(func=cmd_query)

    l = sub.add_parser("list", help="list invoices")
    _add_filters(l)
    l.set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="show all details of one invoice")
    s.add_argument("id", type=int)
    s.set_defaults(func=cmd_show)

    e = sub.add_parser("edit", help="correct extracted fields")
    e.add_argument("id", type=int)
    e.add_argument("--vendor")
    e.add_argument("--number")
    e.add_argument("--date", type=_iso_date, help="YYYY-MM-DD")
    e.add_argument("--amount", type=float)
    e.add_argument("--currency")
    e.add_argument("--notes")
    e.set_defaults(func=cmd_edit)

    pay = sub.add_parser("pay", help="mark invoice(s) as paid")
    pay.add_argument("ids", type=int, nargs="+")
    pay.add_argument("--on", type=_iso_date, help="payment date YYYY-MM-DD (default: today)")
    pay.set_defaults(func=cmd_pay)

    up = sub.add_parser("unpay", help="mark invoice(s) as unpaid again")
    up.add_argument("ids", type=int, nargs="+")
    up.set_defaults(func=cmd_unpay)

    ig = sub.add_parser("ignore", help="mark invoice(s) as not relevant")
    ig.add_argument("ids", type=int, nargs="+")
    ig.set_defaults(func=cmd_ignore)

    sm = sub.add_parser("summary", help="totals per month and currency")
    sm.add_argument("--status", choices=["unpaid", "paid", "ignored"])
    sm.set_defaults(func=cmd_summary)

    x = sub.add_parser("export", help="export invoices to CSV")
    x.add_argument("-o", "--output", default="invoices.csv", help="file path, or - for stdout")
    x.add_argument("--excel", action="store_true", help="Excel (French/European) format: ';' separator, decimal comma")
    _add_filters(x)
    x.set_defaults(func=cmd_export)
    return p


def main(argv: list[str] | None = None) -> int:
    from .gmail import WrongAccountError

    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
        return args.func(cfg, args)
    except (ValueError, FileNotFoundError, WrongAccountError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
