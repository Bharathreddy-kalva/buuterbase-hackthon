"""Finance agent: assesses the financial/contract impact of an event."""

from integrations.butterbase import client
from integrations.evermind import memory

AGENT_ID = "finance"

SYSTEM_PROMPT = """You are the Finance agent for FleetMind, an autonomous \
operations-intelligence system serving ANY industry. You assess the financial \
impact of any incoming event (vendor price change, supply disruption, contract \
expiry, outage, regulatory change, emergency, customer issue, etc.) using the \
organization's current contracts and any relevant past finance cases. If the \
event has no monetary exposure, say so with impact_amount 0.

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
        try:
            contracts = client.select("contracts", params={"order": "value.desc", "limit": 50})
        except Exception:
            contracts = []
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
