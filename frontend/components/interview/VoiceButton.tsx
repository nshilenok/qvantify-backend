import type { VoiceState } from "@/lib/types";

type VoiceButtonProps = {
  state: VoiceState;
  disabled?: boolean;
  onClick: () => void;
};

export default function VoiceButton({ state, disabled, onClick }: VoiceButtonProps) {
  const isRecording = state === "recording";
  const isProcessing = state === "processing";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || isProcessing}
      aria-label={isProcessing ? "Transcribing" : isRecording ? "Stop recording" : "Record voice"}
      className={`flex h-10 w-10 items-center justify-center rounded-full border transition ${
        isRecording
          ? "border-red-500 bg-red-50"
          : isProcessing
            ? "border-slate-300 bg-slate-50 animate-pulse"
            : "border-slate-200 bg-white hover:border-slate-300"
      } ${disabled || isProcessing ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
    >
      {isProcessing ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
      ) : isRecording ? (
        <span className="h-4 w-4 rounded-sm bg-red-600" />
      ) : (
        <svg viewBox="0 0 24 24" className="h-5 w-5 text-slate-600" aria-hidden="true">
          <path
            fill="currentColor"
            d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 1 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z"
          />
        </svg>
      )}
    </button>
  );
}
