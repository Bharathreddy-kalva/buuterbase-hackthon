"""Support agent: identifies affected customers and drafts communications."""

from integrations.butterbase import client
from integrations.evermind import memory

AGENT_ID = "support"

SYSTEM_PROMPT = """You are the Support agent for FleetMind, an autonomous \
operations-intelligence system serving ANY industry. Given any event, the \
organization's current customers, and relevant past support cases, determine \
which clients are affected and draft a short, professional message to send \
them. If no customers are affected, return an empty list and an empty draft.

Respond with ONLY a JSON object, no prose, no markdown fences, in this exact shape:
{
  "affected_clients": [<customer names or ids>],
  "draft_message": <string, a short message to send to affected clients>,
  "action": <string, what support should do next>,
  "reasoning": <string, brief explanation of your assessment>
}"""


class SupportAgent:
    agent_id = AGENT_ID

    def run(self, task, session_id=None):
        try:
            customers = client.select("customers", params={"limit": 50})
        except Exception:
            customers = []
        past_memories = memory.search_memory(self.agent_id, task)

        user_prompt = (
            f"Event:\n{task}\n\n"
            f"Current customers:\n{customers}\n\n"
            f"Past support memories:\n{past_memories}"
        )

        try:
            result = client.chat_completion_json(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            result = {
                "affected_clients": [],
                "draft_message": "",
                "action": f"Unable to complete analysis: {e}",
                "reasoning": str(e),
            }

        memory.store_memory(self.agent_id, session_id, f"Event: {task}\nResult: {result}")
        return result
