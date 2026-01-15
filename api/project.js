import { supabase } from "./_supabase.js";
import { getHeader, json, requireMethod } from "./_utils.js";

const PROJECT_FIELDS = [
  "name",
  "logo",
  "colour",
  "welcome_title",
  "welcome_message",
  "success_title",
  "success_message",
  "abort_title",
  "abort_message",
  "welcome_second_title",
  "welcome_second_message",
  "consent",
  "cta_next",
  "cta_reply",
  "cta_abort",
  "cta_restart",
  "question_title",
  "answer_title",
  "answer_placeholder",
  "loading",
  "collect_email",
  "email_title",
  "email_placeholder",
  "consent_link",
  "skip_welcome",
  "dark_mode",
  "inline_consent",
  "voice_enabled",
];

export default async function handler(req, res) {
  if (!requireMethod(req, res, "GET")) return;

  const projectId = getHeader(req, "projectId");
  if (!projectId) return json(res, 400, { error: "Missing header: projectId" });

  const selectFields = async (fields) =>
    await supabase.from("projects").select(fields.join(",")).eq("id", projectId).limit(1);

  let { data, error } = await selectFields(PROJECT_FIELDS);
  if (error && PROJECT_FIELDS.includes("voice_enabled") && String(error.message || "").includes("voice_enabled")) {
    // Backwards-compatible: if the column doesn't exist yet, retry without it and default to false.
    const fallback = PROJECT_FIELDS.filter((f) => f !== "voice_enabled");
    const retry = await selectFields(fallback);
    data = retry.data;
    error = retry.error;
    if (Array.isArray(data) && data[0] && typeof data[0].voice_enabled === "undefined") {
      data[0].voice_enabled = false;
    }
  }

  if (error) return json(res, 500, { error: error.message });
  if (!data || data.length === 0) return json(res, 404, { error: "Project not found" });

  // Match the existing backend: it returns a JSON array containing one object.
  return json(res, 200, data);
}

