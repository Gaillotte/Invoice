"""Thin wrapper around the Gmail API."""

from __future__ import annotations

import base64
import html
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

# gmail.modify lets us read mail and add a label; it cannot delete mail permanently.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


@dataclass
class Attachment:
    filename: str
    mime_type: str
    attachment_id: str | None
    inline_data: str | None  # small attachments are inlined base64url


@dataclass
class Message:
    id: str
    sender: str
    subject: str
    received_at: datetime
    body_text: str
    attachments: list[Attachment]


def authenticate(credentials_file: Path, token_file: Path, account: str | None = None):
    """Return authorised Google credentials, running the browser OAuth flow if needed."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            # Revoked, or expired (Google expires tokens after 7 days while the
            # Cloud project is in "Testing" mode): sign in again.
            creds = None
    if not (creds and creds.valid):
        if not credentials_file.exists():
            raise FileNotFoundError(
                f"{credentials_file} not found. Create an OAuth client ID (Desktop app) in "
                "Google Cloud Console and download it there — see README."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
        # login_hint pre-selects the configured account on Google's sign-in page.
        creds = flow.run_local_server(port=0, **({"login_hint": account} if account else {}))
    token_file.write_text(creds.to_json())
    token_file.chmod(0o600)
    return creds


def _decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"[ \t ]+", " ", s)


def parse_message(raw: dict) -> Message:
    """Convert a Gmail API message resource (format=full) into a Message."""
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    plain, htmls, attachments = [], [], []

    def walk(part: dict) -> None:
        body = part.get("body", {})
        filename = part.get("filename") or ""
        mime = part.get("mimeType", "")
        if filename:
            attachments.append(
                Attachment(filename, mime, body.get("attachmentId"), body.get("data"))
            )
        elif mime == "text/plain" and body.get("data"):
            plain.append(_decode(body["data"]).decode("utf-8", "replace"))
        elif mime == "text/html" and body.get("data"):
            htmls.append(_html_to_text(_decode(body["data"]).decode("utf-8", "replace")))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    received = datetime.fromtimestamp(int(raw.get("internalDate", "0")) / 1000, tz=timezone.utc)
    return Message(
        id=raw["id"],
        sender=headers.get("from", ""),
        subject=headers.get("subject", ""),
        received_at=received,
        body_text="\n".join(plain) or "\n".join(htmls),
        attachments=attachments,
    )


EXAMPLE_ACCOUNT = "you@gmail.com"  # placeholder in config.example.toml


class WrongAccountError(RuntimeError):
    pass


def check_account(signed_in: str, expected: str | None, token_file: Path) -> None:
    """Fail if the token belongs to another mailbox than the configured account."""
    if expected and signed_in.strip().lower() != expected.strip().lower():
        if expected.strip().lower() == EXAMPLE_ACCOUNT:
            raise WrongAccountError(
                f"Signed in as {signed_in}, but config.toml still has the example address "
                f"account = {expected!r}. Put your own address there, e.g. "
                f'account = "{signed_in}", then run the command again.'
            )
        raise WrongAccountError(
            f"Signed in as {signed_in}, but the config file says account = {expected!r}.\n"
            f"  - If {signed_in} is the right mailbox: change 'account' in the config file.\n"
            f"  - Otherwise: delete {token_file} and run 'invoices auth' to sign in with "
            f"{expected}."
        )


class RateLimitError(RuntimeError):
    """Gmail kept refusing requests for exceeding the per-user quota."""


# Gmail charges 5 quota units for each call we make (list, get, attachment, label) and
# allows about 15,000 units per user per minute; stay well below that.
MAX_CALLS_PER_MINUTE = 1200
RETRY_WAITS = (5, 10, 20, 40, 60)  # seconds, then give up


def _is_rate_limit(exc) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 429:
        return True
    if status == 403:
        try:
            reasons = {e.get("reason") for e in json.loads(exc.content)["error"].get("errors", [])}
        except Exception:
            reasons = set()
        text = str(exc)
        return bool(reasons & {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"}) or (
            "Quota exceeded" in text or "Rate Limit Exceeded" in text
        )
    return False


class GmailClient:
    def __init__(self, creds=None, *, service=None, sleep=time.sleep, clock=time.monotonic, log=print):
        if service is None:
            from googleapiclient.discovery import build

            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        self.service = service
        self._labels: dict[str, str] | None = None
        self._sleep, self._clock, self._log = sleep, clock, log
        self._next_call = 0.0

    def _execute(self, request):
        """Run an API request, pacing calls and waiting out Gmail's per-minute quota."""
        from googleapiclient.errors import HttpError

        for attempt in range(len(RETRY_WAITS) + 1):
            now = self._clock()
            if now < self._next_call:
                self._sleep(self._next_call - now)
            self._next_call = max(now, self._next_call) + 60 / MAX_CALLS_PER_MINUTE
            try:
                return request.execute()
            except HttpError as exc:
                if not _is_rate_limit(exc):
                    raise
                if attempt == len(RETRY_WAITS):
                    raise RateLimitError(
                        "Gmail is still refusing requests (per-minute quota exceeded). "
                        "Wait a few minutes and run 'invoices fetch' again: it continues "
                        "where it stopped."
                    ) from exc
                wait = RETRY_WAITS[attempt]
                self._log(f"  … Gmail rate limit reached, waiting {wait}s before retrying")
                self._sleep(wait)

    def email_address(self) -> str:
        """Address of the mailbox this client is signed in to."""
        return self._execute(self.service.users().getProfile(userId="me"))["emailAddress"]

    def search(self, query: str, limit: int | None = None) -> Iterator[str]:
        """Yield message ids matching a Gmail search query."""
        users = self.service.users()
        token, count = None, 0
        while True:
            resp = self._execute(
                users.messages().list(userId="me", q=query, pageToken=token, maxResults=100)
            )
            for m in resp.get("messages", []):
                yield m["id"]
                count += 1
                if limit and count >= limit:
                    return
            token = resp.get("nextPageToken")
            if not token:
                return

    def get_message(self, message_id: str) -> Message:
        raw = self._execute(self.service.users().messages().get(userId="me", id=message_id, format="full"))
        return parse_message(raw)

    def get_attachment(self, message_id: str, att: Attachment) -> bytes:
        if att.inline_data:
            return _decode(att.inline_data)
        resp = self._execute(
            self.service.users().messages().attachments()
            .get(userId="me", messageId=message_id, id=att.attachment_id)
        )
        return _decode(resp["data"])

    def _label_id(self, name: str) -> str:
        if self._labels is None:
            resp = self._execute(self.service.users().labels().list(userId="me"))
            self._labels = {l["name"]: l["id"] for l in resp.get("labels", [])}
        if name not in self._labels:
            created = self._execute(self.service.users().labels().create(
                userId="me",
                body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
            ))
            self._labels[name] = created["id"]
        return self._labels[name]

    def add_label(self, message_id: str, name: str) -> None:
        self._execute(self.service.users().messages().modify(
            userId="me", id=message_id, body={"addLabelIds": [self._label_id(name)]}
        ))
