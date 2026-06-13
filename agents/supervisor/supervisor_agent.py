"""Supervisor agent: classifies events, fans work out to domain agents,
synthesizes a summary, alerts a human via Photon, and logs the event."""

import asyncio
import json
import uuid

from agents.finance.finance_agent import FinanceAgent
from agents.hr.hr_agent import HRAgent
from agents.logistics.logistics_agent import LogisticsAgent
from agents.support.support_agent import SupportAgent
from integrations.butterbase import client
from integrations.evermind import memory
from integrations.photon import imessage

AGENT_REGISTRY = {
    "finance": FinanceAgent(),
    "hr": HRAgent(),
    "logistics": LogisticsAgent(),
    "support": SupportAgent(),
}

CLASSIFY_SYSTEM_PROMPT = """You are the Supervisor agent for FleetMind, a fleet \
operations orchestrator. Given an incoming event, decide which domain agents \
need to investigate it.

Available agents:
- finance: budgets, contracts, vendor costs, reimbursements
- hr: employees, staffing, escalations needing a person
- logistics: shipments, routes, carriers, warehouses
- support: customers, client communications

Respond with ONLY a JSON object, no prose, no markdown fences, in this exact shape:
{
  "agents": [<subset of "finance", "hr", "logistics", "support">],
  "event_type": <short string classifying the event>,
  "reasoning": <string, brief explanation of why these agents were chosen>
}"""

SYNTHESIZE_SYSTEM_PROMPT = """You are the Supervisor agent for FleetMind. You have \
received findings from one or more domain agents about an event. Write a short \
executive summary (3-5 sentences) suitable for an iMessage alert to an operations \
lead: what happened, the key findings, and the recommended next steps."""


class SupervisorAgent:
    agent_id = "supervisor"

    def classify(self, event_text):
        user_prompt = (
            f"Event:\n{event_text}\n\n"
            f"Available agents: finance, hr, logistics, support."
        )
        try:
            result = client.chat_completion_json(CLASSIFY_SYSTEM_PROMPT, user_prompt)
            agents = [a for a in result.get("agents", []) if a in AGENT_REGISTRY]
        except Exception:
            agents = []
        return agents or list(AGENT_REGISTRY.keys())

    def synthesize(self, event_text, agent_outputs):
        user_prompt = (
            f"Event:\n{event_text}\n\n"
            f"Agent findings:\n{json.dumps(agent_outputs, indent=2, default=str)}"
        )
        try:
            return client.chat_completion(
                [
                    {"role": "system", "content": SYNTHESIZE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=400,
            ).strip()
        except Exception as e:
            return f"Summary unavailable: {e}"

    async def run(self, event):
        event_text = event.get("content") or event.get("summary") or str(event)
        event_id = event.get("id") or f"EVT-{uuid.uuid4().hex[:8]}"

        agent_names = self.classify(event_text)

        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, AGENT_REGISTRY[name].run, event_text, event_id)
            for name in agent_names
        ]
        results = await asyncio.gather(*tasks)
        agent_outputs = dict(zip(agent_names, results))

        summary = self.synthesize(event_text, agent_outputs)

        alert_result = imessage.send_alert(f"FleetMind Alert [{event_id}]\n\n{summary}")

        client.insert(
            "events",
            {
                "id": event_id,
                "type": event.get("type", "unspecified"),
                "source": event.get("source", "api"),
                "content": event_text,
                "summary": summary,
                "agents_triggered": ",".join(agent_names),
                "status": "processed",
            },
        )

        memory.flush_session(event_id)

        return {
            "event_id": event_id,
            "agent_outputs": agent_outputs,
            "summary": summary,
            "alert_sent": alert_result.get("success", False),
        }
