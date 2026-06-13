"""Cross-agent shared memory.

Lets one agent's findings become useful to the others, and records which
agents collaborated on an event and what they decided. Built on top of
`integrations/evermind/memory.py` (EverMind Cloud) for shared learnings and
`integrations/butterbase/client.py` for the durable collaboration log.
"""

from integrations.butterbase import client
from integrations.evermind import memory

SHARED_AGENT_ID = "shared_brain"


def broadcast_learning(source_agent_id, skill, context):
    """Share something one agent learned so every agent can draw on it later."""
    content = f"[from {source_agent_id}] {skill}: {context}"
    return memory.store_memory(SHARED_AGENT_ID, source_agent_id, content)


def get_collective_memory(query):
    """Search the shared brain and every domain agent's memory for relevant context."""
    results = {SHARED_AGENT_ID: memory.search_memory(SHARED_AGENT_ID, query)}
    for agent_id in memory.AGENT_IDS:
        results[agent_id] = memory.search_memory(agent_id, query)
    return results


def log_collaboration(event_id, agents, outcome):
    """Record which agents collaborated on an event and what they decided."""
    return client.insert(
        "collaborations",
        {
            "id": f"COLLAB-{event_id}",
            "event_id": event_id,
            "agents": ",".join(agents),
            "outcome": outcome,
        },
    )
