import type { DebugInfo, InterviewResponse, ProgressState, ProjectConfig, ReplyResponse, RespondentResponse } from "./types";

const parseJson = async <T>(response: Response): Promise<T> => {
  const text = await response.text();
  if (!text) return {} as T;
  return JSON.parse(text) as T;
};

const unwrapProject = (data: ProjectConfig | ProjectConfig[]) => {
  if (Array.isArray(data)) {
    return data[0] || null;
  }
  return data;
};

export const fetchProject = async (projectId: string): Promise<ProjectConfig> => {
  const response = await fetch("/api/project", {
    headers: { projectId },
  });
  if (!response.ok) {
    const payload = await parseJson<{ error?: string }>(response);
    throw new Error(payload.error || "Failed to load project");
  }
  const data = await parseJson<ProjectConfig | ProjectConfig[]>(response);
  const project = unwrapProject(data);
  if (!project) {
    throw new Error("Project not found");
  }
  return project;
};

export const createRespondent = async ({
  projectId,
  externalId,
  email,
  consent,
}: {
  projectId: string;
  externalId: string;
  email?: string;
  consent?: boolean;
}): Promise<RespondentResponse> => {
  const response = await fetch("/api/respondent", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      projectId,
      externalId,
    },
    body: JSON.stringify({ email, consent }),
  });
  if (!response.ok) {
    const payload = await parseJson<{ error?: string }>(response);
    throw new Error(payload.error || "Failed to create respondent");
  }
  return parseJson<RespondentResponse>(response);
};

export const initInterview = async ({
  projectId,
  uuid,
}: {
  projectId: string;
  uuid: string;
}): Promise<InterviewResponse> => {
  const response = await fetch("/api/interview", {
    headers: {
      projectId,
      uuid,
    },
  });
  if (!response.ok) {
    const payload = await parseJson<{ error?: string }>(response);
    throw new Error(payload.error || "Failed to initialize interview");
  }
  return parseJson<InterviewResponse>(response);
};

export const sendReply = async ({
  projectId,
  uuid,
  message,
  voiceInput,
  audioTokens,
}: {
  projectId: string;
  uuid: string;
  message: string;
  voiceInput?: boolean;
  audioTokens?: number;
}): Promise<ReplyResponse> => {
  const response = await fetch("/api/reply", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      projectId,
      uuid,
    },
    body: JSON.stringify({
      message,
      voice_input: Boolean(voiceInput),
      audio_tokens: voiceInput ? audioTokens ?? 0 : 0,
    }),
  });
  if (!response.ok) {
    const payload = await parseJson<{ error?: string }>(response);
    throw new Error(payload.error || "Failed to send reply");
  }
  return parseJson<ReplyResponse>(response);
};

export const transcribeVoice = async ({
  projectId,
  uuid,
  file,
  language,
}: {
  projectId: string;
  uuid: string;
  file: File;
  language?: string;
}): Promise<{ text: string; audioTokens: number }> => {
  const formData = new FormData();
  formData.append("audio", file, file.name || "voice.webm");
  if (language) {
    formData.append("language", language);
  }
  const response = await fetch("/api/voice-transcribe", {
    method: "POST",
    headers: {
      projectId,
      uuid,
    },
    body: formData,
  });
  const data = await parseJson<{ text?: string; audio_tokens?: number; error?: string }>(response);
  if (!response.ok) {
    throw new Error(data.error || "Transcription failed");
  }
  const text = (data.text || "").trim();
  if (!text) {
    throw new Error("No text was generated");
  }
  return { text, audioTokens: Number(data.audio_tokens || 0) };
};

export interface StreamReplyOptions {
  projectId: string;
  uuid: string;
  message: string;
  voiceInput?: boolean;
  audioTokens?: number;
}

export interface StreamReplyResult {
  response: string;
  status: string;
  progress?: ProgressState;
  version?: string;
  _debug?: DebugInfo;
}

/**
 * Send a reply with SSE streaming. Calls `onDelta` for each incremental text
 * chunk, then resolves with the final result.
 *
 * Falls back to a single JSON response when the server doesn't return an
 * event stream (e.g. for non-streamable topic types).
 */
export async function streamReply(
  options: StreamReplyOptions,
  onDelta?: (accumulated: string) => void,
): Promise<StreamReplyResult> {
  const { projectId, uuid, message, voiceInput, audioTokens } = options;

  const response = await fetch("/api/reply", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      Accept: "text/event-stream",
      projectId,
      uuid,
    },
    body: JSON.stringify({
      message,
      stream: true,
      voice_input: Boolean(voiceInput),
      audio_tokens: voiceInput ? audioTokens ?? 0 : 0,
    }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.error || "Failed to send reply");
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("text/event-stream") || !response.body) {
    const payload = await response.json();
    return {
      response: payload.response ?? "",
      status: payload.status ?? "open",
      progress: payload.progress,
      version: payload.version,
      _debug: payload._debug,
    };
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let full = "";
  let finalPayload: StreamReplyResult | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const chunk = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");

      const dataLine = chunk
        .split("\n")
        .map((line) => line.trim())
        .find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      const raw = dataLine.replace(/^data:\s*/, "");
      if (!raw) continue;

      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(raw);
      } catch {
        continue;
      }

      if (payload.type === "delta") {
        const delta = (payload.delta as string) || "";
        if (!delta) continue;
        full += delta;
        onDelta?.(full);
        continue;
      }

      if (payload.type === "final") {
        if (typeof payload.response === "string") {
          full = payload.response;
          onDelta?.(full);
        }
        finalPayload = {
          response: (payload.response as string) ?? full,
          status: (payload.status as string) ?? "open",
          progress: payload.progress as ProgressState | undefined,
          version: payload.version as string | undefined,
          _debug: payload._debug as DebugInfo | undefined,
        };
      }
    }
  }

  return finalPayload ?? { response: full, status: "open" };
}

export * from "./results-api";
