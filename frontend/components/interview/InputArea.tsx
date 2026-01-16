import { useState } from "react";
import type { ProjectConfig } from "@/lib/types";
import { useVoice } from "@/hooks/useVoice";
import VoiceButton from "./VoiceButton";

type InputAreaProps = {
  project: ProjectConfig;
  projectId: string;
  uuid: string | null;
  isSending: boolean;
  onSend: (message: string, meta?: { voiceInput: boolean; audioTokens: number }) => Promise<void> | void;
};

const textValue = (value?: string | null) => (value || "").trim();

export default function InputArea({ project, projectId, uuid, isSending, onSend }: InputAreaProps) {
  const [value, setValue] = useState("");
  const [voiceTokens, setVoiceTokens] = useState(0);
  const voiceEnabled = Boolean(project.voice_enabled);
  const { state, level, start, stop, fileInputRef, handleFileChange, error: voiceError } = useVoice({
    projectId,
    uuid,
    onTranscript: (text, meta) => {
      setValue((prev) => (prev ? `${prev}\n${text}`.trim() : text));
      setVoiceTokens((prev) => prev + (meta.audioTokens || 0));
    },
  });
  const isRecording = state === "recording";
  const isProcessing = state === "processing";

  const canSend = value.trim().length > 0 && !isSending;
  const placeholder = textValue(project.answer_placeholder);
  const ctaReply = textValue(project.cta_reply);
  const waveCount = 9;
  const waveBase = 8;

  const handleSend = async () => {
    if (!canSend) return;
    const next = value.trim();
    const audioTokens = voiceTokens;
    const voiceInput = audioTokens > 0;
    setValue("");
    setVoiceTokens(0);
    await onSend(next, { voiceInput, audioTokens });
  };

  return (
    <div className="flex flex-col gap-4">
      <textarea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder={placeholder}
        rows={4}
        disabled={isSending}
        className={`min-h-[140px] w-full resize-none rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm leading-6 text-slate-900 outline-none transition disabled:opacity-60 ${
          isRecording ? "ring-2 ring-[var(--accent)] ring-offset-2 animate-pulse" : ""
        }`}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            handleSend();
          }
        }}
      />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-h-10 items-center gap-3">
          {voiceEnabled && (
            <>
              <VoiceButton
                state={state}
                disabled={!projectId || !uuid}
                onClick={() => {
                  if (isProcessing) return;
                  if (isRecording) {
                    stop();
                  } else {
                    start();
                  }
                }}
              />
              {isRecording && (
                <div aria-hidden="true" className="flex h-6 items-center gap-1">
                  {Array.from({ length: waveCount }).map((_, index) => {
                    const mid = (waveCount - 1) / 2;
                    const distance = Math.abs(index - mid);
                    const weight = 1 - distance / mid;
                    const amplitude = Math.min(1, level * 8);
                    const height = waveBase + amplitude * (8 + weight * 16);
                    return (
                      <span
                        key={`wave-${index}`}
                        className="w-1 rounded-full bg-slate-400"
                        style={{ height: `${height}px`, transition: "height 80ms ease-out" }}
                      />
                    );
                  })}
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="audio/*"
                capture
                className="hidden"
                onChange={handleFileChange}
              />
            </>
          )}
        </div>
        <button
          type="button"
          onClick={handleSend}
          disabled={!canSend}
          className="cursor-pointer rounded bg-[var(--accent)] px-5 py-2 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-50"
        >
          {ctaReply}
        </button>
      </div>
      {voiceError && (
        <div role="alert" className="text-xs text-red-500">
          {voiceError}
        </div>
      )}
    </div>
  );
}
