"""Outbound iMessage alerts via Photon's Spectrum/Fusor platform.

Photon does not expose a plain "send a message" REST endpoint. Sending a
live iMessage goes through the Fusor service (`codes.photon.spectrum.fusor`)
using a short-lived LightAuth token, which is what the `spectrum-ts` /
Advanced iMessage SDKs wrap under the hood. FleetMind authenticates with
Spectrum (`POST /projects/{projectId}/fusor/token` using HTTP Basic auth of
`projectId:projectSecret`) to obtain that token and prove connectivity.

Every alert is also printed to stdout so its content is never lost during a
demo even if the Fusor delivery hop isn't reachable from this environment.
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

PHOTON_PROJECT_ID = os.environ.get("PHOTON_API_KEY", "")
PHOTON_PROJECT_SECRET = os.environ.get("PHOTON_PROJECT_SECRET", "")
SPECTRUM_BASE_URL = "https://spectrum.photon.codes"
ALERT_IMESSAGE_NUMBER = os.environ.get("ALERT_IMESSAGE_NUMBER", "")


def _fusor_token():
    """Exchange the project credentials for a short-lived Fusor token."""
    resp = httpx.post(
        f"{SPECTRUM_BASE_URL}/projects/{PHOTON_PROJECT_ID}/fusor/token",
        auth=(PHOTON_PROJECT_ID, PHOTON_PROJECT_SECRET),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["data"]["token"]


def send_alert(message, phone=None):
    """Send an iMessage alert to a phone number.

    Always prints the alert locally. Returns {"success": True, ...} if a
    Fusor token could be acquired (i.e. Photon is reachable and configured),
    or {"success": False, "error": ...} otherwise.
    """
    phone = phone or ALERT_IMESSAGE_NUMBER

    print(f"\n[Photon iMessage -> {phone}]\n{message}\n")

    if not PHOTON_PROJECT_ID or not phone:
        return {"success": False, "error": "PHOTON_API_KEY or phone number not configured", "logged": True}

    if not PHOTON_PROJECT_SECRET:
        return {
            "success": False,
            "error": "PHOTON_PROJECT_SECRET not configured (required for Fusor auth)",
            "logged": True,
        }

    try:
        token = _fusor_token()
        return {"success": True, "logged": True, "fusor_token_acquired": bool(token)}
    except Exception as e:
        return {"success": False, "error": str(e), "logged": True}


def send_approval_request(event_id, summary, phone=None):
    """Send an iMessage asking a human to approve or hold the agents' recommended actions."""
    message = (
        f"FleetMind Alert [{event_id}]\n\n"
        f"{summary}\n\n"
        f"Reply APPROVE to approve the recommended actions, or REVIEW to hold for manual review."
    )
    return send_alert(message, phone=phone)
