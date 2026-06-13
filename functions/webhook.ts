// POST /webhook/photon -- inbound Photon Spectrum webhook.
//
// Verifies the HMAC-SHA256 signature, then either:
//  - updates the latest event's status if the message is a short APPROVE/
//    REVIEW reply, or
//  - runs the full FleetMind trigger flow (same logic as functions/trigger.ts,
//    duplicated here since each Edge Function is a standalone deployment)
//    treating the incoming iMessage as a new event.

const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Spectrum-Signature, X-Spectrum-Timestamp",
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

// ---------------------------------------------------------------------
// Signature verification
// ---------------------------------------------------------------------

async function hmacSha256Hex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i++) result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return result === 0;
}

const APPROVE_KEYWORDS = new Set(["APPROVE", "YES", "Y"]);
const REVIEW_KEYWORDS = new Set(["REVIEW", "NO", "N", "HOLD"]);

function classifyReply(text: string): string | null {
  const normalized = text.trim().toUpperCase();
  if (APPROVE_KEYWORDS.has(normalized)) return "approved";
  if (REVIEW_KEYWORDS.has(normalized)) return "needs_review";
  return null;
}

// ---------------------------------------------------------------------
// FleetMind trigger flow (ported from agents/* + supervisor_agent.py)
// ---------------------------------------------------------------------

const DEFAULT_MODEL = "anthropic/claude-sonnet-4.6";

async function chatCompletion(
  ctx: any,
  messages: { role: string; content: string }[],
  maxTokens = 1024,
  temperature = 0.3
): Promise<string> {
  const { BUTTERBASE_APP_ID, BUTTERBASE_API_URL, BUTTERBASE_API_KEY } = ctx.env;
  const resp = await fetch(`${BUTTERBASE_API_URL}/v1/${BUTTERBASE_APP_ID}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${BUTTERBASE_API_KEY}`,
    },
    body: JSON.stringify({ model: DEFAULT_MODEL, messages, max_tokens: maxTokens, temperature }),
  });
  if (!resp.ok) throw new Error(`AI gateway error ${resp.status}: ${await resp.text()}`);
  const data = await resp.json();
  return data.choices?.[0]?.message?.content ?? "";
}

function extractJSON(text: string): any {
  let t = text.trim();
  if (t.startsWith("```")) {
    t = t.replace(/^```[a-zA-Z]*\n?/, "").replace(/```\s*$/, "").trim();
  }
  const start = t.indexOf("{");
  const end = t.lastIndexOf("}");
  if (start === -1 || end === -1) throw new Error(`No JSON object found in model response: ${t}`);
  return JSON.parse(t.slice(start, end + 1));
}

async function chatCompletionJSON(ctx: any, systemPrompt: string, userPrompt: string, maxTokens = 1024): Promise<any> {
  const content = await chatCompletion(
    ctx,
    [
      { role: "system", content: systemPrompt },
      { role: "user", content: userPrompt },
    ],
    maxTokens,
    0.2
  );
  return extractJSON(content);
}

async function evermindPost(ctx: any, path: string, payload: unknown): Promise<any> {
  const base = (ctx.env.EVERMIND_BASE_URL || "https://api.evermind.ai").replace(/\/$/, "");
  try {
    const resp = await fetch(`${base}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${ctx.env.EVERMIND_API_KEY || ""}`,
      },
      body: JSON.stringify(payload),
    });
    return await resp.json();
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

async function searchMemory(ctx: any, agentId: string, query: string): Promise<any> {
  const result = await evermindPost(ctx, "/api/v1/memories/search", {
    query,
    filters: { user_id: agentId },
    method: "hybrid",
    memory_types: ["episodic_memory", "agent_memory"],
    top_k: 5,
  });
  return result.data ?? result;
}

async function storeMemory(ctx: any, agentId: string, sessionId: string, content: string): Promise<any> {
  return evermindPost(ctx, "/api/v1/memories/agent", {
    user_id: agentId,
    session_id: sessionId,
    messages: [{ role: "assistant", timestamp: Date.now(), content }],
  });
}

const AGENT_IDS = ["finance", "hr", "logistics", "support"];

async function flushSession(ctx: any, sessionId: string): Promise<void> {
  await Promise.all(
    AGENT_IDS.map((id) => evermindPost(ctx, "/api/v1/memories/agent/flush", { user_id: id, session_id: sessionId }))
  );
}

const RISK_CATEGORIES = ["financial_risk", "operational_risk", "hr_risk", "customer_risk", "legal_risk", "tech_risk"];

const CLASSIFY_SYSTEM_PROMPT = `You are the Supervisor agent for FleetMind, an autonomous \
operations-intelligence system that can serve ANY industry \
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
}`;

const SYNTHESIZE_SYSTEM_PROMPT = `You are the Supervisor agent for FleetMind. You \
have received findings from one or more domain agents about an event. Write a \
crisp, professional executive summary (3-5 sentences) for a busy executive: \
what happened, the consolidated key findings (quantified where possible), the \
overall risk level, and the single recommended decision. Be industry-neutral \
and specific to the findings — no filler.`;

const ALERT_SYSTEM_PROMPT = `You are FleetMind's Supervisor writing a SHORT iMessage \
to the CFO. Be compelling and actionable in under 480 characters: lead with the \
headline risk and dollar impact if known, then the recommended action. Do not \
add greetings or signatures. Plain text only.`;

const FINANCE_SYSTEM_PROMPT = `You are the Finance agent for FleetMind, an autonomous \
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
}`;

const HR_SYSTEM_PROMPT = `You are the HR agent for FleetMind, an autonomous \
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
}`;

const LOGISTICS_SYSTEM_PROMPT = `You are the Logistics/Operations agent for FleetMind, an \
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
}`;

const SUPPORT_SYSTEM_PROMPT = `You are the Support agent for FleetMind, an autonomous \
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
}`;

const AGENT_CONFIG: Record<string, { table: string; orderBy?: string; prompt: string; fallback: (err: string) => any }> = {
  finance: {
    table: "contracts",
    orderBy: "value DESC",
    prompt: FINANCE_SYSTEM_PROMPT,
    fallback: (err) => ({
      impact_amount: 0,
      affected_contracts: [],
      recommended_action: `Unable to complete analysis: ${err}`,
      confidence: 0.0,
      reasoning: err,
    }),
  },
  hr: {
    table: "employees",
    prompt: HR_SYSTEM_PROMPT,
    fallback: (err) => ({
      affected_staff: [],
      recommended_contacts: [],
      action: `Unable to complete analysis: ${err}`,
      reasoning: err,
    }),
  },
  logistics: {
    table: "shipments",
    prompt: LOGISTICS_SYSTEM_PROMPT,
    fallback: (err) => ({
      affected_shipments: [],
      rerouted_count: 0,
      action: `Unable to complete analysis: ${err}`,
      reasoning: err,
    }),
  },
  support: {
    table: "customers",
    prompt: SUPPORT_SYSTEM_PROMPT,
    fallback: (err) => ({
      affected_clients: [],
      draft_message: "",
      action: `Unable to complete analysis: ${err}`,
      reasoning: err,
    }),
  },
};

async function classify(ctx: any, eventText: string): Promise<{
  agents: string[];
  categories: string[];
  event_type: string;
  severity: string;
}> {
  const userPrompt = `Event:\n${eventText}\n\nAvailable agents: finance, hr, logistics, support.`;
  try {
    const result = await chatCompletionJSON(ctx, CLASSIFY_SYSTEM_PROMPT, userPrompt);
    const agents = (result.agents || []).filter((a: string) => a in AGENT_CONFIG);
    const categories = (result.categories || []).filter((c: string) => RISK_CATEGORIES.includes(c));
    return {
      agents: agents.length ? agents : Object.keys(AGENT_CONFIG),
      categories,
      event_type: result.event_type || "event",
      severity: result.severity || "medium",
    };
  } catch (e) {
    console.error("classify failed", e);
    return { agents: Object.keys(AGENT_CONFIG), categories: [], event_type: "event", severity: "medium" };
  }
}

async function runAgent(ctx: any, agentId: string, eventText: string, sessionId: string): Promise<any> {
  const cfg = AGENT_CONFIG[agentId];
  let rows: any[] = [];
  try {
    const q = cfg.orderBy
      ? `SELECT * FROM ${cfg.table} ORDER BY ${cfg.orderBy} LIMIT 50`
      : `SELECT * FROM ${cfg.table} LIMIT 50`;
    const result = await ctx.db.query(q);
    rows = result.rows;
  } catch (e) {
    console.error(`${agentId} table query failed`, e);
  }

  const pastMemories = await searchMemory(ctx, agentId, eventText);
  const userPrompt =
    `Event:\n${eventText}\n\n` +
    `Current ${cfg.table}:\n${JSON.stringify(rows)}\n\n` +
    `Past ${agentId} memories:\n${JSON.stringify(pastMemories)}`;

  let result: any;
  try {
    result = await chatCompletionJSON(ctx, cfg.prompt, userPrompt);
  } catch (e) {
    result = cfg.fallback(String(e));
  }

  await storeMemory(ctx, agentId, sessionId, `Event: ${eventText}\nResult: ${JSON.stringify(result)}`);
  return result;
}

async function synthesize(ctx: any, eventText: string, agentOutputs: Record<string, any>): Promise<string> {
  const userPrompt = `Event:\n${eventText}\n\nAgent findings:\n${JSON.stringify(agentOutputs, null, 2)}`;
  try {
    return (
      await chatCompletion(
        ctx,
        [
          { role: "system", content: SYNTHESIZE_SYSTEM_PROMPT },
          { role: "user", content: userPrompt },
        ],
        400
      )
    ).trim();
  } catch (e) {
    return `Summary unavailable: ${e}`;
  }
}

async function composeAlert(ctx: any, eventId: string, summary: string, severity: string): Promise<string> {
  let headline = summary;
  try {
    headline = (
      await chatCompletion(
        ctx,
        [
          { role: "system", content: ALERT_SYSTEM_PROMPT },
          { role: "user", content: `Severity: ${severity}\n\nSummary:\n${summary}` },
        ],
        200
      )
    ).trim();
  } catch (e) {
    console.error("composeAlert failed", e);
  }
  return (
    `⚡ FleetMind Alert [${eventId}] · ${severity.toUpperCase()}\n\n` +
    `${headline}\n\n` +
    `Reply APPROVE to execute, or REVIEW to hold.`
  );
}

async function runTrigger(
  ctx: any,
  event: { type?: string; content: string; source?: string; sender?: string }
): Promise<any> {
  const eventText = event.content;
  const eventId = `EVT-${crypto.randomUUID().replace(/-/g, "").slice(0, 8)}`;
  const eventType = event.type || "unspecified";
  const source = event.source || "api";

  const classification = await classify(ctx, eventText);
  const agentNames = classification.agents;

  const agentOutputs: Record<string, any> = {};
  const results = await Promise.all(agentNames.map((name: string) => runAgent(ctx, name, eventText, eventId)));
  agentNames.forEach((name: string, i: number) => (agentOutputs[name] = results[i]));

  const summary = await synthesize(ctx, eventText, agentOutputs);
  const alertMessage = await composeAlert(ctx, eventId, summary, classification.severity);

  console.log(`[Photon iMessage -> ${ctx.env.ALERT_IMESSAGE_NUMBER || "unconfigured"}]\n${alertMessage}`);
  const alertSent = Boolean(ctx.env.ALERT_IMESSAGE_NUMBER);

  try {
    await ctx.db.query(
      "INSERT INTO events (id, type, source, content, summary, agents_triggered, status) VALUES ($1, $2, $3, $4, $5, $6, $7)",
      [
        eventId,
        `${classification.severity} · ${eventType}`,
        source,
        eventText,
        summary,
        agentNames.join(","),
        "processed",
      ]
    );
  } catch (e) {
    console.error(`Failed to log event ${eventId} to Butterbase`, e);
  }

  await flushSession(ctx, eventId);

  return {
    event_id: eventId,
    classification,
    agent_outputs: agentOutputs,
    summary,
    alert_message: alertMessage,
    alert_sent: alertSent,
  };
}

// ---------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------

export default async function handler(req: Request, ctx: any): Promise<Response> {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS_HEADERS });
  if (req.method !== "POST") return json({ error: "method not allowed" }, 405);

  const bodyText = await req.text();
  const timestamp = req.headers.get("X-Spectrum-Timestamp") || "";
  const signature = req.headers.get("X-Spectrum-Signature") || "";

  const secret = ctx.env.PHOTON_WEBHOOK_SECRET || "";
  const expected = await hmacSha256Hex(secret, `v0:${timestamp}:${bodyText}`);
  if (!timingSafeEqual(`v0=${expected}`, signature)) {
    return json({ error: "Invalid signature" }, 401);
  }

  const payload = JSON.parse(bodyText || "{}");
  const eventType = payload.event;
  const data = payload.data || {};
  const text = String(data.text || "").trim();
  const sender = data.from || "";

  if (!text) return json({ received: true, event: eventType });

  // A reply to a pending alert (APPROVE/REVIEW) updates that event's status
  // instead of starting a new run.
  const action = classifyReply(text);
  if (action) {
    const latest = await ctx.db.query(
      "SELECT id FROM events WHERE status = 'processed' ORDER BY created_at DESC LIMIT 1"
    );
    if (latest.rows.length) {
      const id = latest.rows[0].id;
      await ctx.db.query("UPDATE events SET status = $1 WHERE id = $2", [action, id]);
      return json({ received: true, event: eventType, event_id: id, action });
    }
    return json({ received: true, event: eventType, action });
  }

  // Otherwise, the incoming iMessage itself is a new trigger.
  const result = await runTrigger(ctx, { type: "imessage_trigger", source: "imessage", content: text, sender });
  return json({ received: true, event: eventType, result });
}
