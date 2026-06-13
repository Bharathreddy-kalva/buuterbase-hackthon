"""HR agent: identifies which staff need to be looped in on an event."""

from integrations.butterbase import client
from integrations.evermind import memory

AGENT_ID = "hr"

SYSTEM_PROMPT = """You are the HR agent for FleetMind, an autonomous \
operations-intelligence system serving ANY industry. Given any event, the \
organization's current employee roster, and relevant past HR cases, determine \
which staff are affected or should be looped in (by role/responsibility, not \
guesswork), and what HR should do next. If no people action is needed, return \
empty lists and say so.

Respond with ONLY a JSON object, no prose, no markdown fences, in this exact shape:
{
  "affected_staff": [<employee names or ids>],
  "recommended_contacts": [<employee emails to notify>],
  "action": <string, what HR should do next>,
  "reasoning": <string, brief explanation of your assessment>
}"""


class HRAgent:
    agent_id = AGENT_ID

    def run(self, task, session_id=None):
        try:
            employees = client.select("employees", params={"limit": 50})
        except Exception:
            employees = []
        past_memories = memory.search_memory(self.agent_id, task)

        user_prompt = (
            f"Event:\n{task}\n\n"
            f"Current employee roster:\n{employees}\n\n"
            f"Past HR memories:\n{past_memories}"
        )

        try:
            result = client.chat_completion_json(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            result = {
                "affected_staff": [],
                "recommended_contacts": [],
                "action": f"Unable to complete analysis: {e}",
                "reasoning": str(e),
            }

        memory.store_memory(self.agent_id, session_id, f"Event: {task}\nResult: {result}")
        return result
