"""Inbound webhook receiver for Photon's Spectrum messaging events."""

import hashlib
import hmac
import os

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request

from integrations.butterbase import client

load_dotenv()

PHOTON_WEBHOOK_SECRET = os.environ.get("PHOTON_WEBHOOK_SECRET", "")

router = APIRouter()

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
    """Map a reply's text to an event status update, or None if not actionable."""
    normalized = text.strip().upper()
    if any(keyword in normalized for keyword in APPROVE_KEYWORDS):
        return "approved"
    if any(keyword in normalized for keyword in REVIEW_KEYWORDS):
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
    text = data.get("text", "")

    action = _classify_reply(text) if text else None

    if action:
        latest = client.select(
            "events",
            params={"order": "created_at.desc", "limit": 1, "status": "eq.processed"},
        )
        if latest:
            client.update("events", latest[0]["id"], {"status": action})
            return {"received": True, "event": event_type, "event_id": latest[0]["id"], "action": action}

    return {"received": True, "event": event_type, "action": action}
