"""Autonomous Gmail inbox listener.

Polls a Gmail inbox over IMAP every `EMAIL_CHECK_INTERVAL` seconds for new
unread messages. When one arrives, it is turned into a FleetMind trigger event
and run through the Supervisor agent automatically -- no human in the loop
until the CFO approves the resulting alert.

Auth uses a Gmail **App Password** (a 16-digit password generated under your
Google Account -> Security -> App passwords), not your normal login password,
and IMAP must be enabled in Gmail settings.

The listener degrades gracefully: if `EMAIL_USER`/`EMAIL_PASSWORD` are not
configured, it logs once and stays idle so the rest of the app still runs.
"""

import asyncio
import email
import imaplib
import os
from email.header import decode_header
from email.utils import parseaddr

from dotenv import load_dotenv

from agents.supervisor.supervisor_agent import SupervisorAgent

load_dotenv()

EMAIL_HOST = os.environ.get("EMAIL_HOST", "imap.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "993"))
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_CHECK_INTERVAL = int(os.environ.get("EMAIL_CHECK_INTERVAL", "15"))

# Automated/no-reply senders that should never trigger an agent run, and a
# minimum body length below which a message is too short to be a real request.
IGNORED_SENDERS = (
    "no-reply@google.com",
    "no-reply@accounts.google.com",
    "accounts.google.com",
)
IGNORED_SENDER_MARKERS = ("no-reply", "noreply")
MIN_BODY_LENGTH = 50

supervisor = SupervisorAgent()


def is_configured() -> bool:
    return bool(EMAIL_USER and EMAIL_PASSWORD)


def _is_ignored_sender(sender: str) -> bool:
    """True for automated/no-reply senders (Google account notices, etc.)."""
    normalized = sender.lower().strip()
    if any(blocked in normalized for blocked in IGNORED_SENDERS):
        return True
    return any(marker in normalized for marker in IGNORED_SENDER_MARKERS)


def _decode(value) -> str:
    """Decode a possibly RFC 2047-encoded header into a plain string."""
    if not value:
        return ""
    parts = []
    for chunk, enc in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts)


def _extract_body(msg: "email.message.Message") -> str:
    """Pull a readable plaintext body out of an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace").strip()
        # Fall back to HTML if no plaintext part was found.
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace").strip()
        return ""
    payload = msg.get_payload(decode=True)
    if payload:
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace").strip()
    return str(msg.get_payload())


def _fetch_unread() -> list:
    """Blocking IMAP fetch of all unread inbox messages, marking them read.

    Returns a list of {sender, subject, body} dicts. Runs in a thread so it
    never blocks the asyncio event loop.
    """
    emails = []
    conn = imaplib.IMAP4_SSL(EMAIL_HOST, EMAIL_PORT)
    try:
        conn.login(EMAIL_USER, EMAIL_PASSWORD)
        conn.select("INBOX")
        status, data = conn.search(None, "UNSEEN")
        if status != "OK":
            return emails
        ids = data[0].split()
        for msg_id in ids:
            status, msg_data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            sender = parseaddr(_decode(msg.get("From")))[1] or _decode(msg.get("From"))
            subject = _decode(msg.get("Subject"))
            body = _extract_body(msg)
            emails.append({"sender": sender, "subject": subject, "body": body})
            # Mark as read so we don't reprocess it next poll.
            conn.store(msg_id, "+FLAGS", "\\Seen")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        conn.logout()
    return emails


async def _process_email(item: dict) -> None:
    sender = item["sender"]
    subject = item["subject"]
    body = item["body"]
    print(f"\U0001F4E7 Auto-processing email from {sender}: {subject}")
    event = {
        "type": "email",
        "source": sender,
        "content": f"{subject}\n{body}".strip(),
        "raw_subject": subject,
    }
    try:
        await supervisor.run(event)
    except Exception as exc:  # never let one bad email kill the listener
        print(f"⚠️  Email processing failed for {sender}: {exc}")


async def email_listener_loop() -> None:
    """Background task: poll Gmail forever and auto-process new mail."""
    if not is_configured():
        print(
            "\U0001F4EC Email listener idle: set EMAIL_USER and EMAIL_PASSWORD "
            "(Gmail App Password) in .env to enable autonomous inbox watching."
        )
        return

    print(
        f"\U0001F4EC Email listener watching {EMAIL_USER} "
        f"(every {EMAIL_CHECK_INTERVAL}s via {EMAIL_HOST})"
    )
    loop = asyncio.get_event_loop()
    while True:
        try:
            new_mail = await loop.run_in_executor(None, _fetch_unread)
            for item in new_mail:
                sender, subject, body = item["sender"], item["subject"], item["body"]

                if _is_ignored_sender(sender):
                    print(f"🚫 Ignoring automated email from {sender}: {subject}")
                    continue

                if len(body) < MIN_BODY_LENGTH:
                    print(f"🚫 Ignoring short email ({len(body)} chars) from {sender}: {subject}")
                    continue

                await _process_email(item)
        except Exception as exc:
            print(f"⚠️  Email poll error: {exc}")
        await asyncio.sleep(EMAIL_CHECK_INTERVAL)
