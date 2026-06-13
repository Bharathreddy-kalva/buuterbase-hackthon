"""FleetMind FastAPI app: autonomous event intake, live dashboard feed,
agent memory inspection.

On startup it launches the Gmail inbox listener as a background task so new
email arrives and is processed with zero human input. The dashboard receives
real-time updates over the Server-Sent Events endpoint `GET /events/live`.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.supervisor.supervisor_agent import SupervisorAgent
from api.email_listener import (
    EMAIL_USER,
    email_listener_loop,
    is_configured as email_configured,
)
from api.webhook import router as webhook_router
from integrations.butterbase import client
from integrations.evermind import memory
from integrations.photon import imessage
from memory import event_bus

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Launch the autonomous Gmail listener alongside the API."""
    listener = asyncio.create_task(email_listener_loop())
    try:
        yield
    finally:
        listener.cancel()


app = FastAPI(title="FleetMind", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(webhook_router)

supervisor = SupervisorAgent()


class TriggerRequest(BaseModel):
    type: Optional[str] = None
    content: str
    source: Optional[str] = None


@app.get("/health")
def health():
    try:
        client.select("events", params={"limit": 1})
        butterbase_status = "connected"
    except Exception:
        butterbase_status = "disconnected"

    evermind_result = memory.search_memory("supervisor", "health check")
    evermind_status = "disconnected" if "error" in evermind_result else "connected"

    photon_status = "configured" if imessage.ALERT_IMESSAGE_NUMBER else "not configured"

    return {
        "status": "ok",
        "stacks": {
            "butterbase": butterbase_status,
            "evermind": evermind_status,
            "photon": photon_status,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/config")
def config():
    """What FleetMind is autonomously watching — used by the dashboard header."""
    return {
        "email_user": EMAIL_USER or None,
        "email_watching": email_configured(),
        "imessage_number": imessage.ALERT_IMESSAGE_NUMBER or None,
        "env": os.environ.get("ENV", "development"),
    }


@app.post("/trigger")
async def trigger(req: TriggerRequest):
    event = req.model_dump(exclude_none=True)
    return await supervisor.run(event)


@app.get("/events")
def get_events():
    return client.select("events", params={"order": "created_at.desc", "limit": 50})


class DecisionRequest(BaseModel):
    decision: str  # "approve" | "review"


@app.post("/events/{event_id}/decision")
def decide(event_id: str, req: DecisionRequest):
    """CFO decision from the dashboard (APPROVE/REVIEW).

    Mirrors what a real Photon iMessage reply does in api/webhook.py, but
    without the HMAC signature a browser can't produce. Updates the event's
    status in Butterbase and pushes the change to all live dashboards.
    """
    status = "approved" if req.decision.lower().startswith("a") else "needs_review"
    updated = None
    try:
        updated = client.update("events", event_id, {"status": status})
    except Exception as e:
        print(f"⚠️  Failed to update event {event_id} status: {e}")
    event_bus.publish(
        {
            "kind": "event_decision",
            "event_id": event_id,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"event_id": event_id, "status": status, "updated": bool(updated)}


@app.get("/events/live")
async def events_live():
    """Server-Sent Events stream of live FleetMind activity for the dashboard."""

    async def event_stream():
        queue = event_bus.subscribe()
        # Greet the client so it knows the stream is open.
        yield f"data: {json.dumps({'kind': 'connected'})}\n\n"
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(message, default=str)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat keeps proxies/ngrok from closing the connection.
                    yield ": keepalive\n\n"
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/agents/memory/{agent_id}")
def get_agent_memory(agent_id: str, query: str = ""):
    return memory.search_memory(agent_id, query)


@app.get("/agents/skills/{agent_id}")
def get_agent_skills(agent_id: str):
    return memory.get_agent_skills(agent_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=False,
    )
