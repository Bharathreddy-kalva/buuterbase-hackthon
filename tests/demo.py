"""End-to-end demo: an incoming iMessage to FleetMind's Photon number is
delivered as a webhook, parsed as a trigger event, and run through the
supervisor and all four domain agents."""

import hashlib
import hmac
import json
import os
import time

from dotenv import load_dotenv
from fastapi.testclient import TestClient

from api.main import app

load_dotenv()

PHOTON_WEBHOOK_SECRET = os.environ.get("PHOTON_WEBHOOK_SECRET", "")

INCOMING_MESSAGE = (
    "Hey FleetMind - ZYGOS CONSULTING LLC just notified us of a 15% rate "
    "increase on contracts CON-001, CON-003, and CON-006, effective next "
    "month. Can you check the financial impact, see if any staff need to "
    "be looped in, confirm no shipments are disrupted, and draft customer "
    "comms if needed?"
)
INCOMING_SENDER = "+16282688640"


def sign(body, timestamp):
    digest = hmac.new(
        PHOTON_WEBHOOK_SECRET.encode(),
        f"v0:{timestamp}:{body.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"v0={digest}"


def main():
    client = TestClient(app)

    payload = {
        "event": "message.received",
        "data": {"text": INCOMING_MESSAGE, "from": INCOMING_SENDER},
    }
    body = json.dumps(payload).encode()
    timestamp = str(int(time.time()))
    signature = sign(body, timestamp)

    print("=" * 60)
    print("INCOMING iMESSAGE (via Photon webhook -> POST /webhook/photon)")
    print("-" * 60)
    print(f"From: {INCOMING_SENDER}")
    print(f"Text: {INCOMING_MESSAGE}")
    print("=" * 60)

    response = client.post(
        "/webhook/photon",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Spectrum-Timestamp": timestamp,
            "X-Spectrum-Signature": signature,
        },
    )
    response.raise_for_status()
    result = response.json()["result"]

    print("\n" + "=" * 60)
    print(f"Event ID: {result['event_id']}")
    print(f"Alert sent: {result['alert_sent']}")
    print("-" * 60)
    print("Agent outputs:")
    print(json.dumps(result["agent_outputs"], indent=2, default=str))
    print("-" * 60)
    print("Executive summary:")
    print(result["summary"])
    print("=" * 60)


if __name__ == "__main__":
    main()
