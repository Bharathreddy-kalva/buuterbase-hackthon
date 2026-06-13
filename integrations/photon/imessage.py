"""Outbound iMessage alerts via Photon's Spectrum API."""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

PHOTON_API_KEY = os.environ.get("PHOTON_API_KEY", "")
PHOTON_BASE_URL = "https://spectrum.photon.codes"
ALERT_IMESSAGE_NUMBER = os.environ.get("ALERT_IMESSAGE_NUMBER", "")


def _headers():
    return {
        "Authorization": f"Bearer {PHOTON_API_KEY}",
        "Content-Type": "application/json",
    }


def send_alert(message, phone=None):
    """Send a plain iMessage alert to a phone number.

    Returns {"success": True, "response": ...} on success, or
    {"success": False, "error": ...} if the request fails.
    """
    phone = phone or ALERT_IMESSAGE_NUMBER

    if not PHOTON_API_KEY or not phone:
        return {"success": False, "error": "PHOTON_API_KEY or phone number not configured"}

    try:
        resp = httpx.post(
            f"{PHOTON_BASE_URL}/v1/messages",
            headers=_headers(),
            json={"phone": phone, "text": message},
            timeout=15,
        )
        resp.raise_for_status()
        return {"success": True, "response": resp.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_approval_request(event_id, summary, phone=None):
    """Send an iMessage asking a human to approve or hold the agents' recommended actions."""
    message = (
        f"FleetMind Alert [{event_id}]\n\n"
        f"{summary}\n\n"
        f"Reply YES to approve the recommended actions, or NO to hold."
    )
    return send_alert(message, phone=phone)
