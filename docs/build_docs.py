"""Build the Install Guide and User Manual PDFs.

    pip install reportlab
    python docs/build_docs.py

Writes docs/Invoice-Install-Guide.pdf and docs/Invoice-User-Manual.pdf.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    XPreformatted,
)
from reportlab.platypus.tableofcontents import TableOfContents

HERE = Path(__file__).parent
VERSION = "0.1.0"

# --------------------------------------------------------------------------- fonts

FONT_DIRS = [Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu"),
             Path("/Library/Fonts"), Path("C:/Windows/Fonts")]


def _register_fonts() -> tuple[str, str, str]:
    """Use DejaVu (full Unicode) when available, else the PDF base fonts."""
    for d in FONT_DIRS:
        files = {n: d / f for n, f in {
            "Body": "DejaVuSans.ttf", "Body-Bold": "DejaVuSans-Bold.ttf",
            "Body-Oblique": "DejaVuSans-Oblique.ttf", "Mono": "DejaVuSansMono.ttf",
        }.items()}
        if all(p.exists() for p in files.values()):
            for name, path in files.items():
                pdfmetrics.registerFont(TTFont(name, str(path)))
            pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold",
                                          italic="Body-Oblique", boldItalic="Body-Bold")
            return "Body", "Body-Bold", "Mono"
    return "Helvetica", "Helvetica-Bold", "Courier"


BODY, BOLD, MONO = _register_fonts()

# --------------------------------------------------------------------------- styles

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#616e7c")
ACCENT = colors.HexColor("#1d5fa8")
RULE = colors.HexColor("#d9dee4")
CODE_BG = colors.HexColor("#f3f5f7")
TIP_BG, TIP_BAR = colors.HexColor("#eaf3fb"), ACCENT
WARN_BG, WARN_BAR = colors.HexColor("#fdf3e7"), colors.HexColor("#c4701a")

S = {
    "body": ParagraphStyle("body", fontName=BODY, fontSize=10, leading=14.5, textColor=INK,
                           spaceAfter=6, alignment=TA_LEFT),
    "h1": ParagraphStyle("h1", keepWithNext=1, fontName=BOLD, fontSize=17, leading=22, textColor=ACCENT,
                         spaceBefore=4, spaceAfter=10),
    "h2": ParagraphStyle("h2", keepWithNext=1, fontName=BOLD, fontSize=12.5, leading=17, textColor=INK,
                         spaceBefore=12, spaceAfter=5),
    "h3": ParagraphStyle("h3", keepWithNext=1, fontName=BOLD, fontSize=10.5, leading=14, textColor=INK,
                         spaceBefore=8, spaceAfter=3),
    "bullet": ParagraphStyle("bullet", fontName=BODY, fontSize=10, leading=14.5, textColor=INK,
                             leftIndent=14, bulletIndent=3, spaceAfter=2),
    "code": ParagraphStyle("code", fontName=MONO, fontSize=8.4, leading=11.4, textColor=INK),
    "cell": ParagraphStyle("cell", fontName=BODY, fontSize=9, leading=12.5, textColor=INK),
    "cellh": ParagraphStyle("cellh", fontName=BOLD, fontSize=9, leading=12.5, textColor=INK),
    "title": ParagraphStyle("title", fontName=BOLD, fontSize=30, leading=36, textColor=INK),
    "subtitle": ParagraphStyle("subtitle", fontName=BODY, fontSize=14, leading=20, textColor=MUTED),
    "small": ParagraphStyle("small", fontName=BODY, fontSize=9, leading=13, textColor=MUTED),
    "toc1": ParagraphStyle("toc1", fontName=BODY, fontSize=10.5, leading=17, textColor=INK),
}


# --------------------------------------------------------------------------- helpers

def c(text: str) -> str:
    """Inline code."""
    return f'<font face="{MONO}" size="9" color="#0f3d6e">{text}</font>'


S["lead-in"] = ParagraphStyle("lead-in", parent=S["body"], keepWithNext=1)


def p(text: str):
    # A sentence introducing a block ("…, for example:") stays on the same page as it.
    return Paragraph(text, S["lead-in" if text.rstrip().endswith(":") else "body"])


def h1(text: str):
    para = Paragraph(text, S["h1"])
    para._toc = text  # picked up by Doc.afterFlowable
    return para


def h2(text: str):
    return Paragraph(text, S["h2"])


def h3(text: str):
    return Paragraph(text, S["h3"])


def bullets(*items: str):
    return [Paragraph(i, S["bullet"], bulletText="•") for i in items]


def steps(*items: str):
    return [Paragraph(i, S["bullet"], bulletText=f"{n}.") for n, i in enumerate(items, 1)]


CODE_WIDTH = 88  # characters that fit in a code box at this font size


def _wrap_code(text: str) -> str:
    """Hard-wrap long lines (at spaces when possible), indenting continuations."""
    out = []
    for line in text.strip("\n").splitlines():
        indent = "    "
        while len(line) > CODE_WIDTH:
            cut = line.rfind(" ", 0, CODE_WIDTH)
            if cut <= len(indent):
                cut = CODE_WIDTH
            out.append(line[:cut])
            line = indent + line[cut:].lstrip()
        out.append(line)
    return "\n".join(out)


def code(text: str):
    block = XPreformatted(_wrap_code(text).replace("&", "&amp;").replace("<", "&lt;"), S["code"])
    t = Table([[block]], colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return KeepTogether([Spacer(1, 2), t, Spacer(1, 6)])


def _callout(label: str, text: str, bg, bar):
    t = Table([[Paragraph(f"<b>{label}</b>  {text}", S["cell"])]], colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 3, bar),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return KeepTogether([Spacer(1, 2), t, Spacer(1, 8)])


def tip(text: str):
    return _callout("Tip.", text, TIP_BG, TIP_BAR)


def warn(text: str):
    return _callout("Important.", text, WARN_BG, WARN_BAR)


def table(header: list[str], rows: list[list[str]], widths: list[float]):
    data = [[Paragraph(h, S["cellh"]) for h in header]]
    data += [[Paragraph(cell, S["cell"]) for cell in row] for row in rows]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), CODE_BG),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, MUTED),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    t.spaceBefore, t.spaceAfter = 2, 8
    # Short tables move to the next page whole; long ones may split across pages.
    return KeepTogether([t]) if len(rows) < 8 else t


# --------------------------------------------------------------------------- document

class Doc(SimpleDocTemplate):
    def __init__(self, path: Path, title: str):
        super().__init__(str(path), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                         topMargin=22 * mm, bottomMargin=20 * mm, title=title,
                         author="Invoice project", subject=title, creator="docs/build_docs.py")
        self.doc_title = title

    def afterFlowable(self, flowable):
        if hasattr(flowable, "_toc"):
            key = f"h{self.seq.nextf('toc')}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable._toc, key, level=0)
            self.notify("TOCEntry", (0, flowable._toc, self.page, key))

    def _decorate(self, canv, doc):
        if doc.page == 1:
            return
        w, h = A4
        canv.saveState()
        canv.setFont(BODY, 8.5)
        canv.setFillColor(MUTED)
        canv.drawString(22 * mm, h - 13 * mm, f"Invoice — {self.doc_title}")
        canv.drawRightString(w - 22 * mm, 11 * mm, f"Page {doc.page}")
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.5)
        canv.line(22 * mm, h - 15 * mm, w - 22 * mm, h - 15 * mm)
        canv.restoreState()

    def build_story(self, story):
        # Never start a chapter in the last 7 cm of a page.
        story = [x for f in story
                 for x in ([CondPageBreak(70 * mm), f] if hasattr(f, "_toc") else [f])]
        self.multiBuild(story, onFirstPage=self._decorate, onLaterPages=self._decorate)


def cover(title: str, subtitle: str, intro: str):
    toc = TableOfContents()
    toc.levelStyles = [S["toc1"]]
    toc.dotsMinLevel = 0
    return [
        Spacer(1, 45 * mm),
        Paragraph("INVOICE", ParagraphStyle("kicker", fontName=BOLD, fontSize=11,
                                            textColor=ACCENT, leading=14)),
        Spacer(1, 4 * mm),
        Paragraph(title, S["title"]),
        Spacer(1, 3 * mm),
        Paragraph(subtitle, S["subtitle"]),
        Spacer(1, 10 * mm),
        p(intro),
        Spacer(1, 4 * mm),
        Paragraph(f"Version {VERSION} · {date.today():%d %B %Y}", S["small"]),
        PageBreak(),
        Paragraph("Contents", S["h1"]),
        toc,
        PageBreak(),
    ]


# --------------------------------------------------------------------------- install guide

def install_guide():
    s = cover(
        "Install Guide",
        "Setting up Invoice on your computer and connecting it to Gmail",
        "Invoice finds the invoices you receive by email in your Gmail account, saves their "
        "attachments into a folder of your choice and keeps a list of them so you can follow "
        "what is paid and what is not. This guide takes you from nothing to a first import. "
        "Allow about 20 minutes; you only do it once.",
    )

    s += [h1("1. Before you start"),
          p("You will need:"),
          *bullets(
              "A computer running <b>Windows 10/11</b>, <b>macOS</b> or <b>Linux</b>, with a web "
              "browser. The program runs on your own computer; your invoices never leave it.",
              "Your <b>Gmail account</b> (the address and password — the password is typed only "
              "on Google's own sign-in page, never into Invoice).",
              "<b>Python 3.11 or newer</b> (step 2 explains how to install it).",
              "A <b>Google Cloud project</b>, free of charge (step 4). Google requires it for any "
              "program that reads Gmail. No credit card is needed.",
          ),
          p("The installation has seven steps:"),
          table(["Step", "What you do", "Time"], [
              ["2", "Install Python", "5 min"],
              ["3", "Download Invoice and install it", "3 min"],
              ["4", "Create the Google Cloud project and get <i>credentials.json</i>", "10 min"],
              ["5", "Write your configuration file", "2 min"],
              ["6", "Sign in to Gmail", "1 min"],
              ["7", "Check everything and run a first import", "2 min"],
          ], [16, 120, 30]),
          tip(f"In this guide, lines in grey boxes are commands to type in a <b>terminal</b>: "
              f"<i>Terminal</i> on macOS and Linux, <i>PowerShell</i> on Windows (Start menu, "
              f"type “PowerShell”). Press Enter after each line."),
          ]

    s += [h1("2. Install Python"),
          p("First check whether Python is already installed:"),
          code("python3 --version        # macOS / Linux\npy --version             # Windows"),
          p(f"If it prints {c('Python 3.11')} or a higher number, go to step 3. Otherwise:"),
          *bullets(
              "<b>Windows</b>: download the installer from <i>python.org/downloads</i>. On the first "
              "screen, tick <b>“Add python.exe to PATH”</b>, then click <i>Install Now</i>.",
              "<b>macOS</b>: download the installer from <i>python.org/downloads</i> and run it; "
              "or, with Homebrew, run " + c("brew install python") + ".",
              "<b>Linux</b> (Debian/Ubuntu): " + c("sudo apt install python3 python3-venv") + ".",
          ),
          p("Close and reopen the terminal, then run the version check again."),
          ]

    s += [h1("3. Download and install Invoice"),
          h2("3.1 Get the files"),
          p("Either download the project as a ZIP from GitHub (<i>Code › Download ZIP</i>) and "
            "unzip it into a folder such as <i>Documents/Invoice</i>, or, if you use git:"),
          code("git clone https://github.com/gaillotte/invoice.git Invoice"),
          p("Then go into that folder in the terminal:"),
          code("cd Documents/Invoice     # adjust to where you put it"),
          h2("3.2 Install"),
          p("This creates a private Python environment for Invoice (a <i>.venv</i> folder) so it "
            "does not interfere with anything else on your computer:"),
          h3("macOS / Linux"),
          code("python3 -m venv .venv\nsource .venv/bin/activate\npip install -e ."),
          h3("Windows (PowerShell)"),
          code("py -m venv .venv\n.venv\\Scripts\\Activate.ps1\npip install -e ."),
          p(f"When it finishes, check that the {c('invoices')} command works:"),
          code("invoices --help"),
          warn("Each time you open a new terminal to use Invoice, first go to the Invoice folder "
               "and run the <b>activate</b> line again (" + c("source .venv/bin/activate") + " or "
               + c(".venv\\Scripts\\Activate.ps1") + "). Otherwise you will get “command not found”."),
          tip("If Windows refuses to run Activate.ps1 (“running scripts is disabled”), run "
              + c("Set-ExecutionPolicy -Scope CurrentUser RemoteSigned") + " once, then try again."),
          ]

    s += [h1("4. Connect to Google: credentials.json"),
          p("Google does not let programs sign in to Gmail with your password. Instead, you "
            "register Invoice as your own small private app in Google Cloud; Google then gives "
            "you a file, <i>credentials.json</i>, that identifies the app. You sign in with your "
            "account in step 6."),
          p("Google reorganises its console from time to time, so menu names may differ "
            "slightly from those below; the steps stay the same."),
          h2("4.1 Create a project"),
          *steps(
              "Open <b>console.cloud.google.com</b> and sign in with your Gmail account. Accept the "
              "terms if asked.",
              "Click the project selector at the top of the page, then <b>New project</b>. Name it "
              "“Invoice” and click <b>Create</b>. Make sure the new project is selected.",
          ),
          h2("4.2 Enable the Gmail API"),
          *steps(
              "Menu › <b>APIs &amp; Services</b> › <b>Library</b>.",
              "Search for <b>Gmail API</b>, open it and click <b>Enable</b>.",
          ),
          h2("4.3 Describe the app (consent screen)"),
          *steps(
              "Menu › <b>Google Auth Platform</b> (called <i>OAuth consent screen</i> in some "
              "versions) › <b>Get started</b>.",
              "App name: <i>Invoice</i>. User support email: your address. Click Next.",
              "Audience: <b>External</b>. Click Next.",
              "Contact information: your address. Accept the policy and click <b>Create</b>.",
              "Open <b>Audience</b> › <b>Test users</b> › <b>Add users</b>, add <b>your Gmail address</b> "
              "and save. Only addresses listed here can use the app.",
          ),
          warn("Leave the app in <b>Testing</b> mode. Do not click “Publish app”: publishing "
               "would require a security review by Google and is not needed for personal use."),
          h2("4.4 Create the credentials"),
          *steps(
              "Open <b>Clients</b> (or <i>APIs &amp; Services › Credentials › Create credentials › "
              "OAuth client ID</i>).",
              "Application type: <b>Desktop app</b>. Name: <i>Invoice</i>. Click <b>Create</b>.",
              "Click <b>Download JSON</b>.",
              "Move the downloaded file into the Invoice folder and rename it exactly "
              "<b>credentials.json</b>.",
          ),
          tip("credentials.json identifies the app, not you: on its own it gives no access to "
              "your mail. Still, keep it to yourself."),
          ]

    s += [h1("5. Write your configuration"),
          p("Copy the example configuration file:"),
          code("cp config.example.toml config.toml      # macOS / Linux\n"
               "copy config.example.toml config.toml    # Windows"),
          p(f"Open {c('config.toml')} in a text editor (Notepad, TextEdit in plain-text mode, "
            f"VS Code…) and set at least these three lines:"),
          code('account = "your.name@gmail.com"\n'
               'keywords = ["Facture", "Facturation", "Invoice"]\n'
               'invoices_dir = "~/Documents/Factures"'),
          *bullets(
              f"{c('account')}: the Gmail address to manage.",
              f"{c('keywords')}: the words that identify an invoice email (see the User Manual).",
              f"{c('invoices_dir')}: where the invoice files will be saved. {c('~')} means your "
              f"home folder. On Windows you can also write {c('C:/Users/you/Documents/Factures')} "
              f"(use forward slashes).",
          ),
          p("Every other setting has a sensible default; the User Manual describes them all."),
          warn("Do not add your Gmail password to this file. Invoice refuses to start if it "
               "finds a <i>password</i> line, because Google would reject it anyway."),
          ]

    s += [h1("6. Sign in to Gmail"),
          code("invoices auth"),
          *steps(
              "Your browser opens Google's sign-in page, with your account pre-selected.",
              "Google shows <b>“Google hasn't verified this app”</b>. This is expected: it is your "
              "own app from step 4. Click <b>Continue</b>.",
              "Google lists what Invoice asks for: read your email and manage labels. Click "
              "<b>Continue</b>.",
              "The browser says the authentication flow has completed; you can close the tab.",
          ),
          p("The terminal then prints:"),
          code("Authorised as your.name@gmail.com. Token saved to token.json"),
          p(f"The file {c('token.json')} lets Invoice reconnect without asking you again. "
            f"While your Google project is in Testing mode, Google makes this sign-in expire "
            f"after <b>7 days</b>; Invoice then simply opens the sign-in page again."),
          h3("What Invoice can and cannot do with your mailbox"),
          *bullets(
              "It <b>can</b> read your emails and add a label (<i>invoices-processed</i>) to the "
              "ones it has handled.",
              "It <b>cannot</b> send emails, and cannot permanently delete anything.",
              "You can cut its access at any time on <b>myaccount.google.com/permissions</b>.",
          ),
          ]

    s += [h1("7. Check and run a first import"),
          p("Show the search Invoice will use in Gmail:"),
          code("invoices query"),
          code("Account: your.name@gmail.com\n"
               "Invoices folder: /home/you/Documents/Factures\n"
               "Keywords: Facture, Facturation, Invoice\n"
               "Gmail query: has:attachment {subject:Facture subject:Facturation subject:Invoice "
               "filename:Facture filename:Facturation filename:Invoice} "
               "-label:invoices-processed newer_than:1y"),
          tip("Paste the “Gmail query” line into the Gmail search box: you see exactly the "
              "emails Invoice will look at."),
          p("Preview the import without saving anything:"),
          code("invoices fetch --dry-run"),
          p("If the list looks right, import for real, then display the result:"),
          code("invoices fetch\ninvoices list"),
          p("Installation is complete. Continue with the <b>User Manual</b> for everyday use."),
          ]

    s += [h1("8. Troubleshooting"),
          table(["Message or symptom", "What to do"], [
              [f"{c('invoices: command not found')} / “not recognized”",
               "Go to the Invoice folder and activate the environment (step 3.2)."],
              [f"{c('credentials.json not found')}",
               "Put the file downloaded in step 4.4 in the Invoice folder, named exactly "
               "credentials.json (Windows may hide a second “.json”: enable <i>File name "
               "extensions</i> in Explorer's View menu)."],
              ["Google: “Access blocked: Invoice has not completed the Google verification "
               "process” / error 403 access_denied",
               "Your address is not a test user. Add it in step 4.3, point 5."],
              ["Google: “Gmail API has not been used in project … or it is disabled”",
               "Enable the Gmail API (step 4.2), wait a minute, try again."],
              [f"{c('Signed in as … but the config file says account = …')}",
               f"You signed in with another account. Delete {c('token.json')} and run "
               f"{c('invoices auth')} again, choosing the right account."],
              [f"{c(chr(39) + 'password' + chr(39) + ' is not supported')}",
               f"Remove the password line from {c('config.toml')}."],
              [f"{c('Unknown config key')}",
               "A setting name is misspelt in config.toml; compare with config.example.toml."],
              ["The sign-in page opens every week",
               "Normal while the Google project is in Testing mode (see step 6)."],
              ["The browser does not open during sign-in",
               "Copy the long URL printed in the terminal into your browser."],
              [f"{c('fetch')} finds no email",
               f"Run {c('invoices query')} and paste the query into Gmail. Check the keywords "
               f"and the time limit (newer_than), and that the emails have attachments."],
          ], [62, 104]),
          h2("Uninstall"),
          *steps(
              "Revoke access on <b>myaccount.google.com/permissions</b> (entry “Invoice”).",
              "Optionally delete the Google Cloud project (console › IAM &amp; Admin › Settings › "
              "Shut down).",
              "Delete the Invoice folder. Your invoice files in <i>invoices_dir</i> are kept "
              "unless you delete them too.",
          ),
          ]
    return s


# --------------------------------------------------------------------------- user manual

def user_manual():
    s = cover(
        "User Manual",
        "Collecting, checking and following up your Gmail invoices",
        "This manual explains how Invoice works and describes every command and setting. "
        "It assumes Invoice is installed and signed in to Gmail — if not, start with the "
        "Install Guide.",
    )

    s += [h1("1. How Invoice works"),
          p("Each time you run " + c("invoices fetch") + ", Invoice:"),
          *steps(
              "<b>Searches Gmail</b> for emails whose subject or attachment name contains one of "
              "your keywords, that have an attachment, and that it has not handled before.",
              "<b>Downloads the attachments</b> (PDF, images, XML e-invoices) into your invoices "
              "folder, sorted by year and month.",
              "<b>Reads</b> the vendor, invoice number, date, amount and currency from the "
              "document.",
              "<b>Records</b> each invoice in its register, with the status <i>unpaid</i>.",
              "<b>Labels</b> the email <i>invoices-processed</i> in Gmail so it is skipped next "
              "time.",
          ),
          p("You then use the other commands to check the list, correct what was misread, mark "
            "invoices as paid, see monthly totals and export everything to a spreadsheet."),
          h2("Typical routine"),
          code("invoices fetch                  # 1. collect new invoices (e.g. once a week)\n"
               "invoices list --status unpaid   # 2. see what is left to pay\n"
               "invoices edit 5 --amount 240    # 3. fix anything misread (marked ?)\n"
               "invoices pay 2 3                # 4. record payments\n"
               "invoices export --excel -o 2026.csv --since 2026-01-01   # 5. for your accountant"),
          tip("All commands are typed in a terminal, in the Invoice folder, after activating "
              "the environment (see Install Guide, step 3.2). Add " + c("--help") + " to any "
              "command to see its options, e.g. " + c("invoices fetch --help") + "."),
          ]

    s += [h1("2. Choosing which emails are invoices"),
          p(f"The {c('keywords')} list in {c('config.toml')} decides which emails are picked up:"),
          code('keywords = ["Facture", "Facturation", "Invoice"]'),
          p("An email is selected when its <b>subject</b> or the <b>file name of an attachment</b> "
            "contains at least one of these words. The rules come from Gmail search:"),
          *bullets(
              "Upper/lower case does not matter: <i>Facture</i> also finds <i>FACTURE</i> and "
              "<i>facture</i>.",
              "Whole words only: <i>Facture</i> does <b>not</b> find <i>Factures</i> or "
              "<i>Facturation</i>. List every form you want.",
              f"Several words are allowed in one entry: {c(chr(34) + 'Avis de paiement' + chr(34))} "
              f"matches that exact phrase.",
              "The text <i>inside</i> attached PDFs is not searched by Gmail, only the subject and "
              "file names.",
          ),
          h2("Fine-tuning the search"),
          table(["Setting", "Effect", "Example"], [
              [c("require_attachment"), "Only emails with an attachment (default true).",
               c("false")],
              [c("extra_query"), "Extra Gmail search terms added to the search.",
               c('"-from:promo@shop.fr"')],
              [c("newer_than"), "Only emails younger than this. Empty = no limit.",
               f"{c(chr(34) + '30d' + chr(34))}, {c(chr(34) + '6m' + chr(34))}, "
               f"{c(chr(34) + '2y' + chr(34))}"],
              [c("query"), "Replaces the whole keyword-based search with your own Gmail query.",
               c('"from:edf.fr has:attachment"')],
          ], [38, 76, 52]),
          p(f"Run {c('invoices query')} after any change to see the resulting search, and paste "
            f"it into Gmail to check which emails match."),
          h2("Importing older mail"),
          p(f"By default only the last year is searched. For a one-off import of everything:"),
          code('invoices fetch --newer-than ""'),
          ]

    s += [h1("3. Commands"),
          table(["Command", "What it does"], [
              [c("invoices auth"), "Sign in to Gmail (or check the sign-in)."],
              [c("invoices query"), "Show the account, invoices folder, keywords and Gmail search."],
              [c("invoices fetch"), "Import new invoices from Gmail."],
              [c("invoices list"), "List invoices in the register."],
              [c("invoices show ID"), "Show every detail of one invoice."],
              [c("invoices edit ID …"), "Correct the vendor, number, date, amount, currency or notes."],
              [c("invoices pay ID …"), "Mark one or more invoices as paid."],
              [c("invoices unpay ID …"), "Mark invoices as unpaid again."],
              [c("invoices ignore ID …"), "Mark invoices as not relevant (e.g. a quote, a newsletter)."],
              [c("invoices summary"), "Totals per month and currency."],
              [c("invoices export"), "Export the register to a CSV file."],
          ], [48, 118]),
          p(f"{c('ID')} is the number in the first column of {c('invoices list')}. All commands "
            f"accept {c('-c FILE')} before the command name to use another configuration file, "
            f"e.g. {c('invoices -c pro.toml fetch')} for a second mailbox."),
          p(f"Dates are always written <b>YYYY-MM-DD</b> (e.g. {c('2026-11-05')})."),

          h2("3.1 fetch — import new invoices"),
          code("invoices fetch --dry-run"),
          code("Searching Gmail: has:attachment {subject:Facture …} -label:invoices-processed newer_than:1y\n"
               "  + EDF | 2026-10-14 | 87.40 EUR | facture_4471.pdf\n"
               "  + Amazon.fr | 2026-11-04 | 129.00 EUR | Invoice-INV-FR-500118.pdf\n"
               "  - 'Facturation novembre': no matching attachment\n"
               "  = facture_4471_copie.pdf: already in register\n"
               "\n"
               "4 message(s) matched, 0 already processed, 2 invoice(s) added, 1 duplicate(s), 0 error(s)."),
          table(["Mark", "Meaning"], [
              [c("+"), "New invoice: vendor, date, amount and file name."],
              [c("-"), "The email matched but had no attachment of a kept type (see extensions)."],
              [c("="), "This exact file is already in the register (sent twice, reminder email…)."],
              [c("!"), "Error on that email; the others are still processed. Run fetch again later."],
          ], [16, 150]),
          table(["Option", "Effect"], [
              [c("--dry-run"), "Show what would be imported; save nothing, label nothing."],
              [c("-k WORD"), f"Use this keyword instead of the configured ones, for this run "
                             f"only. Repeat for several: {c('-k Facture -k Avoir')}."],
              [c("--newer-than 30d"), f"Override {c('newer_than')}; {c(chr(34)*2)} = no limit."],
              [c("--limit 20"), "Look at no more than 20 emails."],
              [c("--query '…'"), "Use this Gmail search instead of the generated one."],
              [c("--reprocess"), "Look again at emails already handled (files already in the "
                                 "register are still skipped)."],
          ], [40, 126]),

          h2("3.2 list — see the register"),
          code("invoices list --status unpaid"),
          code("ID  Date        Vendor           Number         Amount      Status\n"
               "------------------------------------------------------------------\n"
               "5   2026-11-05  Plombier Martin                          ?  unpaid\n"
               "4   2026-11-04  Amazon EU        INV-FR-500118  129.00 EUR  unpaid\n"
               "3   2026-11-02  Free Mobile                      19.99 EUR  unpaid\n"
               "2   2026-10-20  Orange           F0012845521     39.99 EUR  unpaid"),
          p(f"A {c('?')} means the amount could not be read: correct it with {c('edit')}. When "
            f"the invoice date is unknown, the date shown is the date the email was received."),
          table(["Filter", "Effect"], [
              [c("--status unpaid|paid|ignored"), "Only invoices with this status."],
              [c("--vendor edf"), "Vendor contains this text (case-insensitive)."],
              [c("--since 2026-01-01"), "Invoice date on or after this day."],
              [c("--until 2026-06-30"), "Invoice date on or before this day."],
          ], [56, 110]),
          p(f"Filters can be combined, and work the same with {c('export')}."),

          h2("3.3 show — all details of one invoice"),
          code("invoices show 2"),
          p("Shows the sender, email subject, file name and <b>location of the saved file</b>, "
            "and all invoice fields, status, payment date and notes."),

          h2("3.4 edit — correct an invoice"),
          code('invoices edit 5 --amount 240 --currency EUR --date 2026-11-03 --number 2026-118\n'
               'invoices edit 5 --vendor "Plomberie Martin" --notes "Fuite cuisine"'),
          p(f"Options: {c('--vendor')}, {c('--number')}, {c('--date')}, {c('--amount')} "
            f"(with a dot: {c('240.50')}), {c('--currency')}, {c('--notes')}. Only the options "
            f"you give are changed."),

          h2("3.5 pay, unpay, ignore — follow up"),
          code("invoices pay 2 3                 # paid today\n"
               "invoices pay 4 --on 2026-11-06   # paid on a given day\n"
               "invoices unpay 4                 # undo\n"
               "invoices ignore 7                # not an invoice: hide from unpaid totals"),

          h2("3.6 summary — monthly totals"),
          code("invoices summary"),
          code("Month     Cur   Count         Total  Missing amount\n"
               "2026-11   EUR       3        388.99\n"
               "2026-10   EUR       2        127.39"),
          p(f"Add {c('--status unpaid')} to total only what is left to pay."),
          p("One line per month and currency. <i>Missing amount</i> counts invoices of that "
            "month whose amount is unknown and therefore not in the total."),

          h2("3.7 export — to a spreadsheet"),
          code("invoices export --excel -o factures-2026.csv --since 2026-01-01 --until 2026-12-31"),
          *bullets(
              f"{c('--excel')} writes the format Excel expects in French and most European "
              f"settings (semicolons, decimal comma, accents preserved). Double-click the file to "
              f"open it. Without {c('--excel')} the file uses commas and decimal points, for "
              f"LibreOffice, Google Sheets or English-language Excel.",
              f"{c('-o -')} prints to the screen instead of a file.",
              "The file contains every field, including the path of the saved invoice file.",
          ),
          ]

    s += [h1("4. Where your invoices are stored"),
          table(["What", "Where", "Set by"], [
              ["Invoice files", "<i>invoices_dir</i>/YYYY/MM/", c("invoices_dir")],
              ["Register (the list, statuses, notes)", "<i>data_dir</i>/invoices.db", c("data_dir")],
              ["Google sign-in", "token.json", c("token_file")],
              ["App identity", "credentials.json", c("credentials_file")],
          ], [56, 66, 44]),
          p("Files are named <b>date_vendor_original-name</b>, for example:"),
          code("~/Documents/Factures/2026/10/2026-10-14_EDF_facture_4471.pdf"),
          *bullets(
              "The folder is the <b>invoice date</b> when it could be read, otherwise the date the "
              "email was received.",
              "If the <b>same file</b> arrives twice (identical content), it is saved once.",
              "Two <b>different</b> files with the same name get a short code added to the second "
              "name; nothing is overwritten.",
              f"If you change {c('invoices_dir')}, new invoices go to the new folder; files already "
              f"saved stay where they are and the register still points to them.",
          ),
          tip("Back up the invoices folder and invoices.db together, e.g. by putting both in a "
              "folder synchronised with your cloud storage."),
          ]

    s += [h1("5. How invoice details are read"),
          p("Invoice reads the text of PDF and XML attachments (or, if there is none, the email "
            "itself) and looks for:"),
          table(["Field", "How it is found"], [
              ["Vendor", "The sender's name (e.g. “EDF” from <i>EDF &lt;facture@edf.fr&gt;</i>), "
                         "or the sender's domain if there is no name."],
              ["Amount", "The figure after <i>Net à payer, Montant TTC, Total TTC, Amount due, "
                         "Balance due, Grand total…</i>, or the last “Total”. Both 1 234,56 and "
                         "1,234.56 are understood."],
              ["Currency", "€, $, £ or a code (EUR, USD, GBP, CHF…) next to the amount."],
              ["Invoice number", "The code after <i>Facture n°, Invoice No, Invoice #, Bill</i>…, "
                                 "in the document, then the subject."],
              ["Invoice date", "After <i>Date de facture, Date d'émission, Invoice date, Issue "
                               "date, Date</i>: 14/10/2026, 2026-10-14, 14 octobre 2026, "
                               "October 14, 2026."],
          ], [32, 134]),
          p("This works well for most invoices from companies, but it is a best guess. "
            "<b>Check new invoices</b> with " + c("invoices list") + " and correct with "
            + c("invoices edit") + ". In particular:"),
          *bullets(
              "<b>Scanned invoices</b> (a photo or scan saved as PDF) contain no text, so nothing "
              "can be read: amount, number and date stay empty (shown as ?).",
              "Images (.png, .jpg) are saved but not read.",
              "The vendor is who <i>sent</i> the email: an invoice forwarded by a colleague shows "
              "the colleague's name.",
          ),
          ]

    s += [h1("6. Configuration reference"),
          p(f"All settings live in {c('config.toml')} in the Invoice folder. Text values are "
            f"written between double quotes; lists between square brackets. Lines starting with "
            f"# are comments."),
          table(["Setting", "Default", "Description"], [
              [c("account"), "(empty)", "Gmail address to manage. Pre-selected at sign-in; Invoice "
                                        "refuses to run if signed in to another account."],
              [c("keywords"), c('["Facture", "Facturation", "Invoice"]'),
               "Words searched in the subject and attachment names (chapter 2)."],
              [c("require_attachment"), c("true"), "Only emails with an attachment."],
              [c("extra_query"), "(empty)", "Gmail search terms added to the search."],
              [c("query"), "(empty)", "Full Gmail search replacing the keyword search."],
              [c("newer_than"), c('"1y"'), "Only emails younger than this (d, m, y). Empty = all."],
              [c("processed_label"), c('"invoices-processed"'),
               "Gmail label added to handled emails, which are then skipped. Empty = no label "
               "(Invoice still remembers handled emails in its register)."],
              [c("invoices_dir"), "<i>data_dir</i>/files", "Folder for the invoice files. "
                                                            "~ = home folder."],
              [c("data_dir"), c('"data"'), "Folder for the register invoices.db."],
              [c("extensions"), c('[".pdf", ".png", ".jpg", ".jpeg", ".xml"]'),
               "Attachment types kept; others (logos, signatures…) are ignored."],
              [c("credentials_file"), c('"credentials.json"'), "App identity file from Google."],
              [c("token_file"), c('"token.json"'), "Where the Google sign-in is kept."],
          ], [40, 50, 76]),
          p("Relative paths are relative to the folder you run Invoice from (normally the "
            "Invoice folder)."),
          h3("Example"),
          code('account = "your.name@gmail.com"\n'
               'keywords = ["Facture", "Facturation", "Invoice", "Avis d\'échéance"]\n'
               'extra_query = "-from:newsletter@shop.fr"\n'
               'newer_than = "2y"\n'
               'invoices_dir = "~/Documents/Factures"'),
          ]

    s += [h1("7. Privacy and security"),
          *bullets(
              "Everything runs on your computer. Invoices, the register and the sign-in token "
              "are stored only there; nothing is sent anywhere except requests to Gmail.",
              "Invoice never sees your Google password: you type it on Google's page only.",
              "Its Gmail access is limited to reading emails and adding labels. It cannot send "
              "emails or delete anything permanently.",
              "<b>token.json</b> gives access to your mailbox: do not share it, e-mail it or put "
              "it in a shared folder. If it leaks, revoke access on "
              "<b>myaccount.google.com/permissions</b>; this does not require changing your "
              "password.",
              "The project's .gitignore keeps credentials.json, token.json, config.toml and the "
              "data folder out of git.",
          ),
          ]

    s += [h1("8. Questions and answers"),
          h3("An invoice is missing."),
          p(f"Look for it in Gmail with the query printed by {c('invoices query')}. Usually the "
            f"subject and file name contain none of the keywords (add one), it has no attachment "
            f"(e.g. an invoice to download from a website — download it manually), or it is older "
            f"than {c('newer_than')}. If the email already has the <i>invoices-processed</i> label, "
            f"remove the label in Gmail or use {c('fetch --reprocess')}."),
          h3("An email that is not an invoice was imported."),
          p(f"Use {c('invoices ignore ID')}. To avoid it in future, exclude the sender with "
            f"{c('extra_query')}, e.g. {c(chr(34) + '-from:promo@shop.fr' + chr(34))}."),
          h3("I want to import an email again."),
          p(f"Remove the <i>invoices-processed</i> label from it in Gmail and run "
            f"{c('invoices fetch')}, or run {c('invoices fetch --reprocess')}."),
          h3("I have a second Gmail account."),
          p(f"Create a second configuration file (e.g. {c('pro.toml')}) with its own "
            f"{c('account')}, {c('token_file')} (e.g. {c(chr(34) + 'token-pro.json' + chr(34))}), "
            f"{c('data_dir')} and {c('invoices_dir')}, then use "
            f"{c('invoices -c pro.toml fetch')} and so on."),
          h3("The sign-in page opens again."),
          p("Normal: while the Google project is in Testing mode, Google ends the sign-in after "
            "7 days. Sign in again; nothing is lost."),
          h3("Can I open the saved invoice from the list?"),
          p(f"{c('invoices show ID')} prints its location (file_path); open it from your file "
            f"manager. Files are also easy to browse directly in the invoices folder, by year "
            f"and month."),
          ]
    return s


def main() -> None:
    for name, title, story in [
        ("Invoice-Install-Guide.pdf", "Install Guide", install_guide()),
        ("Invoice-User-Manual.pdf", "User Manual", user_manual()),
    ]:
        path = HERE / name
        Doc(path, title).build_story(story)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
