// GET /memory?agent_id=supervisor&query=... -- search an agent's EverMind
// Cloud memory stream (episodic + agent memories) for relevant past cases.

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

  const url = new URL(req.url);
  const agentId = url.searchParams.get("agent_id") || "supervisor";
  const query = url.searchParams.get("query") || "recent activity";

  const result = await evermindPost(ctx, "/api/v1/memories/search", {
    query,
    filters: { user_id: agentId },
    method: "hybrid",
    memory_types: ["episodic_memory", "agent_memory"],
    top_k: 10,
  });

  return json(result.data ?? result);
}
