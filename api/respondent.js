import crypto from "crypto";

import { supabase } from "./_supabase.js";
import { getHeader, json, readJson, requireMethod } from "./_utils.js";

export default async function handler(req, res) {
  if (!requireMethod(req, res, "POST")) return;

  const projectId = getHeader(req, "projectId");
  const externalId = getHeader(req, "externalId") || null;
  if (!projectId) return json(res, 400, { error: "Missing header: projectId" });

  // Verify project exists
  const { data: proj, error: projErr } = await supabase
    .from("projects")
    .select("id")
    .eq("id", projectId)
    .limit(1);
  if (projErr) return json(res, 500, { error: projErr.message });
  if (!proj || proj.length === 0) return json(res, 404, { error: "Project not found" });

  const body = (await readJson(req)) || {};
  const email = body.email ?? null;
  const consent = Boolean(body.consent);

  const uuid = crypto.randomUUID();
  const createdAt = new Date().toISOString();

  const { error: insErr } = await supabase.from("respondents").insert({
    id: uuid,
    created_at: createdAt,
    project: projectId,
    email,
    consent,
    external_id: externalId,
  });
  if (insErr) return json(res, 500, { error: insErr.message });

  return json(res, 200, { uuid, projectId });
}

