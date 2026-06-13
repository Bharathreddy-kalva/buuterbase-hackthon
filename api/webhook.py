"""Inbound webhook receiver for Photon's Spectrum messaging events."""

import hashlib
import hmac
import os

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request

load_dotenv()

PHOTON_WEBHOOK_SECRET = os.environ.get("PHOTON_WEBHOOK_SECRET", "")

router = APIRouter()


def verify_signature(timestamp, signature, body):
    """Verify a Spectrum webhook signature (HMAC-SHA256 of "v0:{timestamp}:{body}")."""
    expected = hmac.new(
        PHOTON_WEBHOOK_SECRET.encode(),
        f"v0:{timestamp}:{body.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"v0={expected}", signature or "")


@router.post("/webhook/photon")
async def photon_webhook(request: Request):
    body = await request.body()
    timestamp = request.headers.get("X-Spectrum-Timestamp", "")
    signature = request.headers.get("X-Spectrum-Signature", "")

    if not verify_signature(timestamp, signature, body):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    return {"received": True, "event": payload.get("event")}
