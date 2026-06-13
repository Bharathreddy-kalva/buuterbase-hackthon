// GET  /events            -- list FleetMind events, most recent first.
// POST /events             { event_id, decision: "approve" | "review" }
//      -- CFO decision from the dashboard, mirrors a Photon iMessage reply.

const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

export default async function handler(req: Request, ctx: any): Promise<Response> {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS_HEADERS });

  if (req.method === "GET") {
    const result = await ctx.db.query(
      "SELECT * FROM events ORDER BY created_at DESC LIMIT 50"
    );
    return json(result.rows);
  }

  if (req.method === "POST") {
    const body = await req.json().catch(() => ({} as any));
    const eventId = body.event_id;
    if (!eventId) return json({ error: "event_id is required" }, 400);

    const decision = String(body.decision || "").toLowerCase();
    const status = decision.startsWith("a") ? "approved" : "needs_review";

    const result = await ctx.db.query(
      "UPDATE events SET status = $1 WHERE id = $2 RETURNING *",
      [status, eventId]
    );
    return json({ event_id: eventId, status, updated: result.rows.length > 0 });
  }

  return json({ error: "method not allowed" }, 405);
}
