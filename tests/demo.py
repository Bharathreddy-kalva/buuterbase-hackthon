"""End-to-end demo: a vendor rate-increase event flows through the supervisor
and out to the finance, logistics, and support agents."""

import asyncio
import json

from agents.supervisor.supervisor_agent import SupervisorAgent

EVENT = {
    "type": "vendor_rate_increase",
    "source": "email",
    "content": (
        "Subject: Urgent - Vendor Rate Increase Notice\n\n"
        "ZYGOS CONSULTING LLC has notified us of a 15% rate increase on its "
        "consulting and advisory contracts (CON-001, CON-003, CON-006), effective "
        "next month. This will raise our monthly spend and may require us to pass "
        "costs through to affected customer accounts. Please assess the financial "
        "impact, confirm whether any staff need to be looped in, check whether any "
        "shipments are disrupted, and prepare customer communications if needed."
    ),
}


async def main():
    supervisor = SupervisorAgent()
    result = await supervisor.run(EVENT)

    print("=" * 60)
    print(f"Event ID: {result['event_id']}")
    print(f"Alert sent: {result['alert_sent']}")
    print("-" * 60)
    print("Agent outputs:")
    print(json.dumps(result["agent_outputs"], indent=2, default=str))
    print("-" * 60)
    print("Executive summary:")
    print(result["summary"])
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
