import type { InterviewResponse, ProjectConfig, ReplyResponse, RespondentResponse } from "./types";

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

export * from "./results-api";
