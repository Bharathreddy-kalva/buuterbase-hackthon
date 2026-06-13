"""FleetMind FastAPI app: trigger events, receive webhooks, inspect agent memory."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from agents.supervisor.supervisor_agent import SupervisorAgent
from api.webhook import router as webhook_router
from integrations.butterbase import client
from integrations.evermind import memory
from integrations.photon import imessage

app = FastAPI(title="FleetMind")
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


@app.post("/trigger")
async def trigger(req: TriggerRequest):
    event = req.model_dump(exclude_none=True)
    return await supervisor.run(event)


@app.get("/events")
def get_events():
    return client.select("events", params={"order": "created_at.desc", "limit": 50})


@app.get("/agents/memory/{agent_id}")
def get_agent_memory(agent_id: str, query: str = ""):
    return memory.search_memory(agent_id, query)


@app.get("/agents/skills/{agent_id}")
def get_agent_skills(agent_id: str):
    return memory.get_agent_skills(agent_id)


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=False)
