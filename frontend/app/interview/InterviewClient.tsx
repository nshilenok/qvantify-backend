"use client";

import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { createRespondent, initInterview, streamReply } from "@/lib/api";
import type { DebugInfo, Message, ProgressState } from "@/lib/types";
import { useProject } from "@/hooks/useProject";
import WelcomeScreen from "@/components/interview/WelcomeScreen";
import InputArea from "@/components/interview/InputArea";
import ProgressBar from "@/components/interview/ProgressBar";
import SuccessScreen from "@/components/interview/SuccessScreen";

type Phase = "loading" | "welcome" | "conversation" | "success" | "error";

function logDebug(label: string, debug: DebugInfo | undefined) {
  if (!debug) return;
  if (typeof window !== "undefined" && window.location.hostname !== "localhost"
      && window.location.hostname !== "127.0.0.1") return;
  console.log(
    `%c[qvantify debug] ${label}`,
    "color:#684EAD;font-weight:bold",
    debug,
  );
}

const FE_VERSION = process.env.NEXT_PUBLIC_BUILD_SHA || "dev";

const createMessage = (role: "assistant" | "user", content: string): Message => ({
  id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  role,
  content,
});

export default function InterviewClient() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("interview");
  const externalIdParam =
    searchParams.get("external_id") || searchParams.get("externalId") || "";
  const externalIdRef = useRef<string | null>(null);
  if (!externalIdRef.current) {
    externalIdRef.current = externalIdParam || `guest_${Date.now()}`;
  }

  const { project, loading: projectLoading, error: projectError } = useProject(projectId);
  const [phase, setPhase] = useState<Phase>("loading");
  const beVersionLogged = useRef(false);
  const [uuid, setUuid] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [aborted, setAborted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [sessionKey, setSessionKey] = useState<string | null>(null);
  const [resumeUuid, setResumeUuid] = useState<string | null>(null);
  const [streamingResponse, setStreamingResponse] = useState<string | null>(null);
  const [streamingStarted, setStreamingStarted] = useState(false);
  const [streamingActive, setStreamingActive] = useState(false);

  const accent = useMemo(() => project?.colour || "#684EAD", [project]);
  const questionTitle = useMemo(
    () => (project?.question_title || "").trim(),
    [project?.question_title]
  );
  const currentPrompt = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const message = messages[i];
      if (message.role === "assistant") return message.content;
    }
    return "";
  }, [messages]);
  const displayPrompt = streamingResponse || currentPrompt;
  const shimmerStyle = useMemo(
    () => ({
      backgroundImage:
        "linear-gradient(90deg, #e5e5e5 0%, #e5e5e5 40%, #efefef 50%, #e5e5e5 60%, #e5e5e5 100%)",
      backgroundSize: "300% 100%",
      backgroundPosition: "200% 0",
      animation: "qv-shimmer 5.4s ease-in-out infinite",
    }),
    []
  );
  const showShimmer =
    ((phase === "conversation" || phase === "loading") && !displayPrompt) ||
    (isSending && !streamingStarted);
  const isInputDisabled = isSending || !displayPrompt;
  const hasStartedRef = useRef(false);
  const resumeUuidRef = useRef<string | null>(null);

  const logBeVersion = useCallback((version: string | undefined) => {
    if (beVersionLogged.current || !version) return;
    beVersionLogged.current = true;
    console.log(`[qvantify] FE: ${FE_VERSION} | BE: ${version}`);
  }, []);

  useEffect(() => {
    console.log(`[qvantify] FE: ${FE_VERSION}`);
  }, []);

  useEffect(() => {
    resumeUuidRef.current = resumeUuid;
  }, [resumeUuid]);

  useEffect(() => {
    if (!streamingActive && streamingResponse && streamingResponse === currentPrompt) {
      setStreamingResponse(null);
    }
  }, [currentPrompt, streamingActive, streamingResponse]);

  useEffect(() => {
    if (!projectId) return;
    setSessionReady(false);

    let resolvedExternalId = externalIdParam.trim();
    if (!resolvedExternalId) {
      try {
        resolvedExternalId =
          localStorage.getItem(`qv-interview-last-external:${projectId}`) || "";
      } catch {
        resolvedExternalId = "";
      }
    }
    if (!resolvedExternalId) {
      resolvedExternalId = `guest_${Date.now()}`;
    }
    externalIdRef.current = resolvedExternalId;

    const key = `qv-interview-session:${projectId}:${resolvedExternalId}`;
    setSessionKey(key);

    let storedUuid: string | null = null;
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed.uuid === "string") {
          storedUuid = parsed.uuid;
        }
      }
      localStorage.setItem(`qv-interview-last-external:${projectId}`, resolvedExternalId);
    } catch {
      storedUuid = null;
    }

    setResumeUuid(storedUuid);
    setUuid(storedUuid);
    setSessionReady(true);
  }, [externalIdParam, projectId]);

  const persistSession = useCallback(
    (uuidToStore: string) => {
      if (!sessionKey) return;
      try {
        localStorage.setItem(
          sessionKey,
          JSON.stringify({ uuid: uuidToStore, updatedAt: Date.now() })
        );
      } catch {
        // ignore storage issues
      }
    },
    [sessionKey]
  );

  const clearSession = useCallback(() => {
    if (!sessionKey) return;
    try {
      localStorage.removeItem(sessionKey);
    } catch {
      // ignore storage issues
    }
    setResumeUuid(null);
    setUuid(null);
  }, [sessionKey]);

  const startInterview = useCallback(
    async ({ email, consent }: { email?: string; consent: boolean }) => {
      if (!projectId || !externalIdRef.current) {
        setError("Missing interview link parameters.");
        setPhase("error");
        return;
      }
      if (!sessionReady) {
        return;
      }
      if (hasStartedRef.current) return;
      hasStartedRef.current = true;
      setIsStarting(true);
      setError(null);
      try {
        const runInterview = async (activeUuid: string) => {
          setUuid(activeUuid);
          const initial = await initInterview({ projectId, uuid: activeUuid });
          logBeVersion(initial.version);
          logDebug("initInterview", initial._debug);
          setMessages([createMessage("assistant", initial.response)]);
          setProgress(initial.progress || null);
          if (initial.status === "closed") {
            setPhase("success");
          } else {
            setPhase("conversation");
          }
        };

        const storedUuid = resumeUuidRef.current;
        if (storedUuid) {
          await runInterview(storedUuid);
          return;
        }

        const respondent = await createRespondent({
          projectId,
          externalId: externalIdRef.current,
          email,
          consent,
        });
        setResumeUuid(respondent.uuid);
        persistSession(respondent.uuid);
        await runInterview(respondent.uuid);
        return;
      } catch (err) {
        if (resumeUuidRef.current) {
          clearSession();
          try {
            const respondent = await createRespondent({
              projectId,
              externalId: externalIdRef.current,
              email,
              consent,
            });
            setResumeUuid(respondent.uuid);
            persistSession(respondent.uuid);
            const initial = await initInterview({ projectId, uuid: respondent.uuid });
            logBeVersion(initial.version);
            logDebug("initInterview (retry)", initial._debug);
            setMessages([createMessage("assistant", initial.response)]);
            setProgress(initial.progress || null);
            if (initial.status === "closed") {
              setPhase("success");
            } else {
              setPhase("conversation");
            }
            return;
          } catch (retryError) {
            const message =
              retryError instanceof Error ? retryError.message : "Failed to start interview";
            setError(message);
            setPhase("error");
            return;
          }
        }
        const message = err instanceof Error ? err.message : "Failed to start interview";
        setError(message);
        setPhase("error");
      } finally {
        setIsStarting(false);
      }
    },
    [clearSession, logBeVersion, persistSession, projectId, sessionReady]
  );

  const handleSend = useCallback(
    async (message: string, meta?: { voiceInput: boolean; audioTokens: number }) => {
      if (!projectId || !uuid) return;
      setIsSending(true);
      setStreamingActive(true);
      setStreamingStarted(false);
      setStreamingResponse(null);
      setMessages((prev) => [...prev, createMessage("user", message)]);
      try {
        let started = false;
        const markStarted = () => {
          if (started) return;
          started = true;
          setStreamingStarted(true);
        };

        const result = await streamReply(
          {
            projectId,
            uuid,
            message,
            voiceInput: meta?.voiceInput,
            audioTokens: meta?.voiceInput ? meta?.audioTokens : undefined,
          },
          (accumulated) => {
            markStarted();
            setStreamingResponse(accumulated);
          },
        );

        logBeVersion(result.version);
        logDebug("reply", result._debug);

        if (result.response) {
          setMessages((prev) => [...prev, createMessage("assistant", result.response)]);
        }
        setProgress(result.progress || null);
        if (result.status === "closed") {
          setPhase("success");
        }
      } catch (err) {
        const messageText = err instanceof Error ? err.message : "Failed to send reply";
        setError(messageText);
      } finally {
        setIsSending(false);
        setStreamingActive(false);
        setStreamingStarted(false);
      }
    },
    [projectId, uuid]
  );

  useEffect(() => {
    if (projectLoading) return;
    if (projectError) {
      setError(projectError);
      setPhase("error");
      return;
    }
    if (!project) return;
    if (project.skip_welcome) {
      startInterview({ consent: true });
    } else {
      setPhase("welcome");
    }
  }, [project, projectError, projectLoading, sessionReady, startInterview]);

  if (!projectId) {
    return (
      <div className="flex min-h-[100svh] bg-[#f7f7f7]">
        <div className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center px-10 pb-10 pt-8 text-center box-border">
          <h1 className="text-sm font-semibold text-slate-900">Missing interview link</h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">Please check the URL and try again.</p>
        </div>
      </div>
    );
  }

  if (projectLoading || !project) {
    return (
      <div className="flex min-h-[100svh] bg-[#f7f7f7]">
        <div className="flex flex-1 items-center justify-center px-10 pb-10 pt-8 text-sm text-slate-600 box-border">
          Loading interview…
        </div>
      </div>
    );
  }

  if (phase === "welcome") {
    return (
      <div style={{ "--accent": accent } as CSSProperties} className="flex min-h-[100svh] bg-[#f7f7f7]">
        <WelcomeScreen project={project} isStarting={isStarting} onStart={startInterview} />
      </div>
    );
  }

  if (phase === "success") {
    return (
      <div style={{ "--accent": accent } as CSSProperties} className="flex min-h-[100svh] bg-[#f7f7f7]">
        <SuccessScreen
          project={project}
          aborted={aborted}
          onRestart={() => {
            clearSession();
            if (typeof window !== "undefined") {
              window.location.assign(window.location.href);
              return;
            }
            setMessages([]);
            setProgress(null);
            setAborted(false);
            hasStartedRef.current = false;
            setPhase(project.skip_welcome ? "loading" : "welcome");
          }}
        />
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className="flex min-h-[100svh] bg-[#f7f7f7]">
        <div className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center px-10 pb-10 pt-8 text-center box-border">
          <h1 className="text-sm font-semibold text-slate-900">Something went wrong</h1>
          <p className="mt-2 text-sm leading-6 text-red-500">{error || "Please try again later."}</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ "--accent": accent } as CSSProperties} className="flex min-h-[100svh] flex-col bg-[#f7f7f7]">
      <ProgressBar progress={progress} accent={accent} />
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-10 pb-10 pt-8 box-border">
        <div className="flex justify-end">
          <button
            type="button"
            className="cursor-pointer text-xs font-normal text-slate-400 transition hover:text-slate-500"
            onClick={() => {
              setAborted(true);
              setPhase("success");
            }}
          >
            {project.cta_abort}
          </button>
        </div>

        <div className="mt-8 flex flex-1 flex-col gap-8">
          <div className="flex flex-col gap-3">
            {questionTitle && (
              <p className="text-sm font-semibold text-slate-600">{questionTitle}</p>
            )}
            {showShimmer ? (
              <div aria-busy="true" aria-live="polite" className="flex flex-col gap-2">
                <div className="h-4 w-11/12 rounded" style={shimmerStyle} />
                <div className="h-4 w-8/12 rounded" style={shimmerStyle} />
                <span className="sr-only">Loading</span>
              </div>
            ) : (
              <p className="text-sm leading-6 text-slate-900">{displayPrompt}</p>
            )}
          </div>

          <InputArea
            project={project}
            projectId={projectId}
            uuid={uuid}
            isSending={isInputDisabled}
            onSend={handleSend}
          />
        </div>
      </div>
    </div>
  );
}
