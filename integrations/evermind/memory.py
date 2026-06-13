"""Agent memory backed directly by a Butterbase table (no vector search).

Memories are stored as rows in the "agent_memories" table:
  - agent_id:   which agent the memory belongs to (e.g. "finance")
  - session_id: which conversation/session the memory came from
  - content:    the memory text
  - timestamp:  when the memory was recorded

Retrieval is a simple "ilike" text filter scoped to an agent (and
optionally a session) rather than embedding-based vector search.
"""

from integrations.butterbase import client

TABLE = "agent_memories"


def store_memory(agent_id, content, session_id=None):
    """Save a new memory for an agent and return the created row."""
    return client.insert(
        TABLE,
        {
            "agent_id": agent_id,
            "session_id": session_id,
            "content": content,
        },
    )


def search_memories(agent_id, query=None, session_id=None, limit=10):
    """Return an agent's memories, optionally filtered by a text query.

    `query` is matched against `content` with a case-insensitive
    substring search (ILIKE %query%).
    """
    params = {
        "agent_id": f"eq.{agent_id}",
        "order": "timestamp.desc",
        "limit": limit,
    }
    if session_id is not None:
        params["session_id"] = f"eq.{session_id}"
    if query:
        params["content"] = f"ilike.%{query}%"

    return client.select(TABLE, params=params)


def get_recent_memories(agent_id, session_id=None, limit=10):
    """Return an agent's most recent memories, regardless of content."""
    return search_memories(agent_id, query=None, session_id=session_id, limit=limit)
