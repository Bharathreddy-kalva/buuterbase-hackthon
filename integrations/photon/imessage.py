"""Photon iMessage integration.

Photon's real role in FleetMind is INBOUND: an employee texts the FleetMind
iMessage number, Photon delivers that message to POST /webhook/photon, and
that message becomes a trigger event for the supervisor agent (see
api/webhook.py). That's the demo's primary "iMessage as input" flow.

Photon's Spectrum API has no general-purpose REST endpoint for *sending*
iMessages (only project/webhook/token management routes exist), so
send_alert() below "sends" an alert by printing it to the console and
appending it to photon_outbox.json in the project root -- giving the demo a
clear, durable record of every alert FleetMind would have sent.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ALERT_IMESSAGE_NUMBER = os.environ.get("ALERT_IMESSAGE_NUMBER", "")
OUTBOX_PATH = Path(__file__).resolve().parents[2] / "photon_outbox.json"


def send_alert(message, phone=None):
    """"Send" an iMessage alert.

    Prints the alert to the console and appends it to photon_outbox.json.
    """
    phone = phone or ALERT_IMESSAGE_NUMBER

    print(f"\n{'=' * 60}")
    print(f"[Photon iMessage -> {phone}]")
    print("-" * 60)
    print(message)
    print("=" * 60 + "\n")

    outbox = []
    if OUTBOX_PATH.exists():
        try:
            outbox = json.loads(OUTBOX_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            outbox = []
    outbox.append({"to": phone, "message": message})
    OUTBOX_PATH.write_text(json.dumps(outbox, indent=2))

    return {"success": True, "method": "console", "message": message}


def send_approval_request(event_id, summary, phone=None):
    """Send an iMessage asking a human to approve or hold the agents' recommended actions."""
    message = (
        f"FleetMind Alert [{event_id}]\n\n"
        f"{summary}\n\n"
        f"Reply APPROVE to approve the recommended actions, or REVIEW to hold for manual review."
    )
    return send_alert(message, phone=phone)
