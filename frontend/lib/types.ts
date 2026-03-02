export interface ProjectConfig {
  name?: string | null;
  logo?: string | null;
  colour?: string | null;
  welcome_title?: string | null;
  welcome_message?: string | null;
  welcome_second_title?: string | null;
  welcome_second_message?: string | null;
  consent?: string | null;
  consent_link?: string | null;
  cta_next?: string | null;
  cta_reply?: string | null;
  cta_abort?: string | null;
  cta_restart?: string | null;
  question_title?: string | null;
  answer_title?: string | null;
  answer_placeholder?: string | null;
  success_title?: string | null;
  success_message?: string | null;
  abort_title?: string | null;
  abort_message?: string | null;
  collect_email?: boolean | null;
  email_title?: string | null;
  email_placeholder?: string | null;
  skip_welcome?: boolean | null;
  dark_mode?: boolean | null;
  inline_consent?: boolean | null;
  voice_enabled?: boolean | null;
}

export interface ProgressState {
  current: number;
  total: number;
  ratio: number;
}

export interface DebugInfo {
  model: string | null;
  reasoning_effort: string | null;
  topic_title: string | null;
  user_id: string | null;
  external_id: string | null;
  developer_prompt: string | null;
}

export interface InterviewResponse {
  response: string;
  status: "open" | "closed" | string;
  answers?: unknown[];
  progress?: ProgressState;
  version?: string;
  _debug?: DebugInfo;
}

export type ReplyResponse = InterviewResponse;

export interface RespondentResponse {
  uuid: string;
  projectId: string;
}

export interface Message {
  id: string;
  role: "assistant" | "user";
  content: string;
}

export type VoiceState = "idle" | "recording" | "processing";
