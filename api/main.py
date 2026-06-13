"""FleetMind FastAPI app: trigger events, receive webhooks, inspect agent memory."""

from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from agents.supervisor.supervisor_agent import SupervisorAgent
from api.webhook import router as webhook_router
from integrations.evermind import memory

app = FastAPI(title="FleetMind")
app.include_router(webhook_router)

supervisor = SupervisorAgent()


class TriggerRequest(BaseModel):
    id: Optional[str] = None
    type: Optional[str] = None
    source: Optional[str] = None
    content: str
    summary: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/trigger")
async def trigger(req: TriggerRequest):
    event = req.model_dump(exclude_none=True)
    return await supervisor.run(event)


@app.get("/agents/memory/{agent_id}")
def get_agent_memory(agent_id: str, query: str = ""):
    return memory.search_memory(agent_id, query)


@app.get("/agents/skills/{agent_id}")
def get_agent_skills(agent_id: str):
    return memory.get_agent_skills(agent_id)
