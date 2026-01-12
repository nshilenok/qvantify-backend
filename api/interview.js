import { supabase } from "./_supabase.js";
import { getHeader, json, requireMethod } from "./_utils.js";

export default async function handler(req, res) {
  if (!requireMethod(req, res, "GET")) return;

  const projectId = getHeader(req, "projectId");
  const uuid = getHeader(req, "uuid");
  if (!projectId) return json(res, 400, { error: "Missing header: projectId" });
  if (!uuid) return json(res, 400, { error: "Missing header: uuid" });

  // Verify respondent exists for project
  const { data: resp, error: respErr } = await supabase
    .from("respondents")
    .select("id, project")
    .eq("id", uuid)
    .limit(1);
  if (respErr) return json(res, 500, { error: respErr.message });
  if (!resp || resp.length === 0 || resp[0].project !== projectId) {
    return json(res, 404, { error: "Respondent not found for this project" });
  }

  // Fetch first topic
  const { data: topics, error: topicErr } = await supabase
    .from("topics")
    .select("id, system, topic_type, defined_answers")
    .eq("project", projectId)
    .order("sequence", { ascending: true })
    .limit(1);
  if (topicErr) return json(res, 500, { error: topicErr.message });
  if (!topics || topics.length === 0) return json(res, 404, { error: "No topics found" });

  const topic = topics[0];
  const now = new Date().toISOString();

  // Create topics_log entry if one doesn't exist yet
  // (match Python behavior: first call creates a log entry)
  const { data: existingLog, error: logErr } = await supabase
    .from("topics_log")
    .select("id")
    .eq("user_id", uuid)
    .eq("topic_id", topic.id)
    .limit(1);
  if (logErr) return json(res, 500, { error: logErr.message });

  if (!existingLog || existingLog.length === 0) {
    const { error: insLogErr } = await supabase.from("topics_log").insert({
      topic_id: topic.id,
      user_id: uuid,
      started_at: now,
      status: 1,
      responses: 0,
    });
    if (insLogErr) return json(res, 500, { error: insLogErr.message });
  }

  // Store assistant message in records (this matches what we observed from the Python backend for single_question)
  const { error: insRecErr } = await supabase.from("records").insert({
    created_at: now,
    project: projectId,
    role: "assistant",
    content: topic.system,
    topic: topic.id,
    user_id: uuid,
  });
  if (insRecErr) return json(res, 500, { error: insRecErr.message });

  return json(res, 200, {
    response: topic.system,
    status: "open",
    answers: topic.defined_answers || [],
  });
}

