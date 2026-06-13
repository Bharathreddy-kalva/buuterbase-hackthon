"""Agent memory backed by the EverMind Cloud API.

Each FleetMind agent gets its own memory stream in EverMind, addressed by
`user_id=agent_id`. A single orchestration run shares a `session_id` (the
event id) across all agents involved, so their memories can be flushed
together once the run finishes.

Every call degrades gracefully: if EverMind is unreachable or returns an
error, these functions return an empty/error result instead of raising, so
a memory outage never breaks an agent run.
"""

import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

EVERMIND_BASE_URL = os.environ.get("EVERMIND_BASE_URL", "https://api.evermind.ai").rstrip("/")
EVERMIND_API_KEY = os.environ.get("EVERMIND_API_KEY", "")

AGENT_IDS = ["finance", "hr", "logistics", "support"]


def _headers():
    return {
        "Authorization": f"Bearer {EVERMIND_API_KEY}",
        "Content-Type": "application/json",
    }


def _post(path, payload):
    resp = httpx.post(f"{EVERMIND_BASE_URL}{path}", headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def store_memory(agent_id, session_id, content):
    """Record a memory for an agent's session in EverMind."""
    try:
        return _post(
            "/api/v1/memories/agent",
            {
                "user_id": agent_id,
                "session_id": session_id,
                "messages": [
                    {
                        "role": "assistant",
                        "timestamp": int(time.time() * 1000),
                        "content": content,
                    }
                ],
            },
        )
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_memory(agent_id, query):
    """Search an agent's past episodes and cases for relevant context."""
    try:
        result = _post(
            "/api/v1/memories/search",
            {
                "query": query,
                "filters": {"user_id": agent_id},
                "method": "hybrid",
                "memory_types": ["episodic_memory", "agent_memory"],
                "top_k": 5,
            },
        )
        return result.get("data", {})
    except Exception as e:
        return {"success": False, "error": str(e)}


def flush_session(session_id):
    """Trigger EverMind to extract/consolidate memories for a session.

    A FleetMind session spans every agent the supervisor dispatched to, so
    this flushes agent memory for each known agent under that session id.
    """
    results = {}
    for agent_id in AGENT_IDS:
        try:
            results[agent_id] = _post(
                "/api/v1/memories/agent/flush",
                {"user_id": agent_id, "session_id": session_id},
            )
        except Exception as e:
            results[agent_id] = {"success": False, "error": str(e)}
    return results


def get_agent_skills(agent_id):
    """Return the self-evolving skills EverMind has distilled for an agent."""
    try:
        result = _post(
            "/api/v1/memories/get",
            {
                "memory_type": "agent_skill",
                "filters": {"user_id": agent_id},
                "page_size": 20,
            },
        )
        return result.get("data", {}).get("agent_skills", [])
    except Exception as e:
        return []
