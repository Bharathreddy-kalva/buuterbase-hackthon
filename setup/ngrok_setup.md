# Exposing FleetMind to Photon with ngrok

Photon delivers inbound iMessages to FleetMind by calling a webhook URL. When
you run FleetMind locally, that URL (`http://localhost:8000`) isn't reachable
from the internet. [ngrok](https://ngrok.com) gives your local server a public
HTTPS URL that Photon can reach.

## 1. Install ngrok

**macOS (Homebrew):**

```bash
brew install ngrok
```

**Or download directly:** https://ngrok.com/download

Then add your auth token (free account at https://dashboard.ngrok.com):

```bash
ngrok config add-authtoken <YOUR_NGROK_AUTHTOKEN>
```

## 2. Start FleetMind

In one terminal:

```bash
python api/main.py
# FleetMind listens on http://localhost:8000
```

## 3. Start the ngrok tunnel

In a second terminal:

```bash
ngrok http 8000
```

ngrok prints a public forwarding URL, e.g.:

```
Forwarding   https://a1b2-34-56-78-90.ngrok-free.app -> http://localhost:8000
```

Copy that HTTPS URL. Optionally store it in `.env` as `NGROK_URL` for reference.

## 4. Point Photon at the webhook

In your Photon project settings (https://app.photon.codes), set the inbound
message webhook to:

```
https://<your-ngrok-url>/webhook/photon
```

Photon will sign each request; FleetMind verifies it with
`PHOTON_WEBHOOK_SECRET` from your `.env`.

## 5. Test it

**Send a real iMessage** to your `ALERT_IMESSAGE_NUMBER`. Within a couple of
seconds you should see the Supervisor run in the FleetMind console and a new
event appear on the dashboard.

**Or test the endpoint with curl** (this uses a deliberately invalid signature,
so it should return `401` — proving signature verification is active):

```bash
curl -i -X POST https://<your-ngrok-url>/webhook/photon \
  -H "Content-Type: application/json" \
  -H "X-Spectrum-Timestamp: 0" \
  -H "X-Spectrum-Signature: v0=invalid" \
  -d '{"event":"message.received","data":{"text":"hello","from":"+10000000000"}}'
# HTTP/1.1 401 Unauthorized  (expected — signature check works)
```

To exercise the full agent flow locally without a signature, use the demo
script instead, which signs the payload correctly:

```bash
python tests/demo.py
```

## Notes

- The free ngrok URL changes every restart — update the Photon webhook each
  time, or use a reserved domain on a paid plan.
- ngrok's web inspector at http://localhost:4040 shows every webhook Photon
  sends, which is handy for debugging.
- Keep both terminals (FleetMind + ngrok) running for the duration of the demo.
