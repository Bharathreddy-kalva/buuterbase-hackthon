"""Logistics agent: assesses shipment impact of an event."""

from integrations.butterbase import client
from integrations.evermind import memory

AGENT_ID = "logistics"

SYSTEM_PROMPT = """You are the Logistics/Operations agent for FleetMind, an \
autonomous operations-intelligence system serving ANY industry. Given any \
event, the organization's current shipments/operations, and relevant past \
cases, determine which operations are disrupted and what should be done next \
(rerouting, expediting, contingency). If nothing operational is affected, \
return empty lists and say so.

Respond with ONLY a JSON object, no prose, no markdown fences, in this exact shape:
{
  "affected_shipments": [<shipment id strings>],
  "rerouted_count": <integer, number of shipments that need rerouting>,
  "action": <string, what logistics should do next>,
  "reasoning": <string, brief explanation of your assessment>
}"""


class LogisticsAgent:
    agent_id = AGENT_ID

    def run(self, task, session_id=None):
        try:
            shipments = client.select("shipments", params={"limit": 50})
        except Exception:
            shipments = []
        past_memories = memory.search_memory(self.agent_id, task)

        user_prompt = (
            f"Event:\n{task}\n\n"
            f"Current shipments:\n{shipments}\n\n"
            f"Past logistics memories:\n{past_memories}"
        )

        try:
            result = client.chat_completion_json(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            result = {
                "affected_shipments": [],
                "rerouted_count": 0,
                "action": f"Unable to complete analysis: {e}",
                "reasoning": str(e),
            }

        memory.store_memory(self.agent_id, session_id, f"Event: {task}\nResult: {result}")
        return result
