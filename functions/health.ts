// GET /health -- FleetMind stack status for the dashboard header.
// Checks Butterbase DB connectivity and EverMind Cloud reachability.

const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
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

export default async function handler(req: Request, ctx: any): Promise<Response> {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS_HEADERS });

  let butterbase = "disconnected";
  try {
    await ctx.db.query("SELECT 1");
    butterbase = "connected";
  } catch (e) {
    console.error("butterbase health check failed", e);
  }

  let evermind = "disconnected";
  try {
    const result = await evermindPost(ctx, "/api/v1/memories/search", {
      query: "health check",
      filters: { user_id: "supervisor" },
      method: "hybrid",
      memory_types: ["episodic_memory", "agent_memory"],
      top_k: 1,
    });
    evermind = result && result.error ? "disconnected" : "connected";
  } catch (e) {
    console.error("evermind health check failed", e);
  }

  const photon = ctx.env.ALERT_IMESSAGE_NUMBER ? "configured" : "not configured";

  return json({
    status: "ok",
    stacks: { butterbase, evermind, photon },
    imessage_number: ctx.env.ALERT_IMESSAGE_NUMBER || null,
    env: ctx.env.ENV || "production",
    timestamp: new Date().toISOString(),
  });
}
