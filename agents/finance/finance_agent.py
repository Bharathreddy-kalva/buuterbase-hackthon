"""Finance agent: assesses the financial/contract impact of an event."""

from integrations.butterbase import client
from integrations.evermind import memory

AGENT_ID = "finance"

SYSTEM_PROMPT = """You are the Finance agent for FleetMind, a fleet operations \
orchestrator. You assess the financial impact of incoming events (vendor \
notices, rate changes, contract amendments, emergencies, etc.) using the \
company's current contracts and any relevant past finance cases.

Respond with ONLY a JSON object, no prose, no markdown fences, in this exact shape:
{
  "impact_amount": <number, estimated dollar impact of this event>,
  "affected_contracts": [<contract id strings>],
  "recommended_action": <string, what finance should do next>,
  "confidence": <number between 0 and 1>,
  "reasoning": <string, brief explanation of your assessment>
}"""


class FinanceAgent:
    agent_id = AGENT_ID

    def run(self, task, session_id=None):
        contracts = client.select("contracts", params={"order": "value.desc", "limit": 50})
        past_memories = memory.search_memory(self.agent_id, task)

        user_prompt = (
            f"Event:\n{task}\n\n"
            f"Current contracts:\n{contracts}\n\n"
            f"Past finance memories:\n{past_memories}"
        )

        try:
            result = client.chat_completion_json(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            result = {
                "impact_amount": 0,
                "affected_contracts": [],
                "recommended_action": f"Unable to complete analysis: {e}",
                "confidence": 0.0,
                "reasoning": str(e),
            }

        memory.store_memory(self.agent_id, session_id, f"Event: {task}\nResult: {result}")
        return result
