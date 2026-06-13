"""Supervisor agent: classifies events, fans work out to domain agents,
synthesizes a summary, alerts a human via Photon, and logs the event.

Industry-agnostic: the supervisor makes no assumptions about what business
FleetMind is running. It classifies any incoming event into generic risk
categories and routes it to whichever domain agents are relevant.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

from agents.finance.finance_agent import FinanceAgent
from agents.hr.hr_agent import HRAgent
from agents.logistics.logistics_agent import LogisticsAgent
from agents.support.support_agent import SupportAgent
from integrations.butterbase import client
from integrations.evermind import memory
from integrations.photon import imessage
from memory import event_bus
from memory.shared_brain import log_collaboration

AGENT_REGISTRY = {
    "finance": FinanceAgent(),
    "hr": HRAgent(),
    "logistics": LogisticsAgent(),
    "support": SupportAgent(),
}

# Generic risk categories an event can fall into, independent of industry.
RISK_CATEGORIES = [
    "financial_risk",
    "operational_risk",
    "hr_risk",
    "customer_risk",
    "legal_risk",
    "tech_risk",
]

CLASSIFY_SYSTEM_PROMPT = """You are the Supervisor agent for FleetMind, an \
autonomous operations-intelligence system that can serve ANY industry \
(logistics, SaaS, retail, healthcare, finance, manufacturing, etc.). An event \
has arrived — it could be a vendor price increase, a supply disruption, a \
contract expiry, a staff emergency, a customer complaint, a system outage, a \
regulatory change, or anything else.

Classify the event and decide which domain agents must investigate it. Choose \
the smallest set of agents that genuinely need to act.

Domain agents:
- finance: any monetary/contract/budget/cost/payment exposure
- hr: any people impact — staff to notify, safety, staffing, escalation to a person
- logistics: any operational/supply/delivery/service-continuity impact
- support: any customer- or client-facing impact or communications needed

Risk categories (pick all that apply): financial_risk, operational_risk, \
hr_risk, customer_risk, legal_risk, tech_risk.

Respond with ONLY a JSON object, no prose, no markdown fences, in this exact shape:
{
  "agents": [<subset of "finance", "hr", "logistics", "support">],
  "categories": [<subset of the risk categories above>],
  "event_type": <short human-readable label for this event>,
  "severity": <"low" | "medium" | "high" | "critical">,
  "reasoning": <one sentence on why these agents/categories were chosen>
}"""

SYNTHESIZE_SYSTEM_PROMPT = """You are the Supervisor agent for FleetMind. You \
have received findings from one or more domain agents about an event. Write a \
crisp, professional executive summary (3-5 sentences) for a busy executive: \
what happened, the consolidated key findings (quantified where possible), the \
overall risk level, and the single recommended decision. Be industry-neutral \
and specific to the findings — no filler."""

ALERT_SYSTEM_PROMPT = """You are FleetMind's Supervisor writing a SHORT iMessage \
to the CFO. Be compelling and actionable in under 480 characters: lead with the \
headline risk and dollar impact if known, then the recommended action. Do not \
add greetings or signatures. Plain text only."""


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
            categories = [c for c in result.get("categories", []) if c in RISK_CATEGORIES]
            event_type = result.get("event_type", "event")
            severity = result.get("severity", "medium")
        except Exception:
            agents, categories, event_type, severity = [], [], "event", "medium"
        return {
            "agents": agents or list(AGENT_REGISTRY.keys()),
            "categories": categories,
            "event_type": event_type,
            "severity": severity,
        }

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

    def compose_alert(self, event_id, summary, severity):
        """Build the CFO iMessage text (LLM-written, with a safe fallback)."""
        try:
            headline = client.chat_completion(
                [
                    {"role": "system", "content": ALERT_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Severity: {severity}\n\nSummary:\n{summary}"},
                ],
                max_tokens=200,
            ).strip()
        except Exception:
            headline = summary
        return (
            f"⚡ FleetMind Alert [{event_id}] · {severity.upper()}\n\n"
            f"{headline}\n\n"
            f"Reply APPROVE to execute, or REVIEW to hold."
        )

    async def run(self, event):
        event_text = event.get("content") or event.get("summary") or str(event)
        event_id = event.get("id") or f"EVT-{uuid.uuid4().hex[:8]}"
        event_type = event.get("type", "unspecified")
        source = event.get("source", "api")
        now = datetime.now(timezone.utc).isoformat()

        classification = self.classify(event_text)
        agent_names = classification["agents"]

        # Tell the dashboard a new event is being worked on, and which agents.
        event_bus.publish(
            {
                "kind": "event_received",
                "event_id": event_id,
                "type": event_type,
                "source": source,
                "content": event_text,
                "agents": agent_names,
                "categories": classification["categories"],
                "event_type": classification["event_type"],
                "severity": classification["severity"],
                "status": "processing",
                "timestamp": now,
            }
        )

        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, AGENT_REGISTRY[name].run, event_text, event_id)
            for name in agent_names
        ]
        results = await asyncio.gather(*tasks)
        agent_outputs = dict(zip(agent_names, results))

        summary = self.synthesize(event_text, agent_outputs)

        alert_message = self.compose_alert(event_id, summary, classification["severity"])
        alert_result = imessage.send_alert(alert_message)

        try:
            client.insert(
                "events",
                {
                    "id": event_id,
                    # Prefix the event type with severity so the history table can
                    # surface it without a schema change (e.g. "high · email").
                    "type": f"{classification['severity']} · {event_type}",
                    "source": source,
                    "content": event_text,
                    "summary": summary,
                    "agents_triggered": ",".join(agent_names),
                    "status": "processed",
                },
            )
        except Exception as e:
            print(f"⚠️  Failed to log event {event_id} to Butterbase: {e}")

        memory.flush_session(event_id)
        try:
            log_collaboration(event_id, agent_names, summary)
        except Exception:
            pass

        # Tell the dashboard the run is complete with all results.
        event_bus.publish(
            {
                "kind": "event_complete",
                "event_id": event_id,
                "type": event_type,
                "source": source,
                "severity": classification["severity"],
                "agent_outputs": agent_outputs,
                "summary": summary,
                "alert_message": alert_message,
                "alert_sent": alert_result.get("success", False),
                "status": "processed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        return {
            "event_id": event_id,
            "classification": classification,
            "agent_outputs": agent_outputs,
            "summary": summary,
            "alert_message": alert_message,
            "alert_sent": alert_result.get("success", False),
        }
