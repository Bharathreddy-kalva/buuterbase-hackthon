"""Inbound webhook receiver for Photon's Spectrum messaging events.

This is FleetMind's primary Photon integration: when someone texts the
FleetMind iMessage number, Photon delivers the message here as a webhook,
and -- unless it's a reply to a pending alert (APPROVE/REVIEW) -- that text
becomes a new trigger event run through the supervisor and its domain
agents. iMessage is the input trigger to FleetMind.
"""

import hashlib
import hmac
import os

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request

from agents.supervisor.supervisor_agent import SupervisorAgent
from integrations.butterbase import client

load_dotenv()

PHOTON_WEBHOOK_SECRET = os.environ.get("PHOTON_WEBHOOK_SECRET", "")

router = APIRouter()
supervisor = SupervisorAgent()

APPROVE_KEYWORDS = ("APPROVE", "YES", "Y")
REVIEW_KEYWORDS = ("REVIEW", "NO", "N", "HOLD")


def verify_signature(timestamp, signature, body):
    """Verify a Spectrum webhook signature (HMAC-SHA256 of "v0:{timestamp}:{body}")."""
    expected = hmac.new(
        PHOTON_WEBHOOK_SECRET.encode(),
        f"v0:{timestamp}:{body.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"v0={expected}", signature or "")


def _classify_reply(text):
    """Map a short reply (e.g. "APPROVE", "Y") to an event status update,
    or None if this isn't a short actionable reply (e.g. a new request)."""
    normalized = text.strip().upper()
    if normalized in APPROVE_KEYWORDS:
        return "approved"
    if normalized in REVIEW_KEYWORDS:
        return "needs_review"
    return None


@router.post("/webhook/photon")
async def photon_webhook(request: Request):
    body = await request.body()
    timestamp = request.headers.get("X-Spectrum-Timestamp", "")
    signature = request.headers.get("X-Spectrum-Signature", "")

    if not verify_signature(timestamp, signature, body):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event_type = payload.get("event")
    data = payload.get("data", {})
    text = data.get("text", "").strip()
    sender = data.get("from", "")

    if not text:
        return {"received": True, "event": event_type}

    # A reply to a pending alert (APPROVE/REVIEW) updates that event's status
    # instead of starting a new run.
    action = _classify_reply(text)
    if action:
        latest = client.select(
            "events",
            params={"order": "created_at.desc", "limit": 1, "status": "eq.processed"},
        )
        if latest:
            client.update("events", latest[0]["id"], {"status": action})
            return {"received": True, "event": event_type, "event_id": latest[0]["id"], "action": action}
        return {"received": True, "event": event_type, "action": action}

    # Otherwise, the incoming iMessage itself is a new trigger: run it
    # through the supervisor and its domain agents.
    result = await supervisor.run(
        {
            "type": "imessage_trigger",
            "source": "imessage",
            "content": text,
            "sender": sender,
        }
    )
    return {"received": True, "event": event_type, "result": result}
