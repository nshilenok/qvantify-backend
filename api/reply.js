import { supabase } from "./_supabase.js";
import { getHeader, json, readJson, requireMethod } from "./_utils.js";

export default async function handler(req, res) {
  if (!requireMethod(req, res, "POST")) return;

  const projectId = getHeader(req, "projectId");
  const uuid = getHeader(req, "uuid");
  if (!projectId) return json(res, 400, { error: "Missing header: projectId" });
  if (!uuid) return json(res, 400, { error: "Missing header: uuid" });

  const body = (await readJson(req)) || {};
  const message = typeof body.message === "string" ? body.message : "";
  if (!message) return json(res, 400, { error: "Missing JSON field: message" });

  const now = new Date().toISOString();

  // Store user message
  const { error: userErr } = await supabase.from("records").insert({
    created_at: now,
    project: projectId,
    role: "user",
    content: message,
    topic: null,
    user_id: uuid,
  });
  if (userErr) return json(res, 500, { error: userErr.message });

  // Minimal behavior for now: echo acknowledgement.
  // (Full AI behavior can be layered in once OPENAI_API_KEY is configured on a backend that can call OpenAI.)
  const reply = "Thanks — noted.";

  const { error: asstErr } = await supabase.from("records").insert({
    created_at: new Date().toISOString(),
    project: projectId,
    role: "assistant",
    content: reply,
    topic: null,
    user_id: uuid,
  });
  if (asstErr) return json(res, 500, { error: asstErr.message });

  return json(res, 200, { response: reply, status: "open", answers: [] });
}

