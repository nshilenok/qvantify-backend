import type { ProjectConfig } from "@/lib/types";

type SuccessScreenProps = {
  project: ProjectConfig;
  aborted: boolean;
  onRestart?: () => void;
};

const textValue = (value?: string | null) => (value || "").trim();

export default function SuccessScreen({ project, aborted, onRestart }: SuccessScreenProps) {
  const successTitle = textValue(project.success_title);
  const successMessage = textValue(project.success_message);
  const abortTitle = textValue(project.abort_title);
  const abortMessage = textValue(project.abort_message);
  const title = aborted ? abortTitle || successTitle : successTitle;
  const message = aborted ? abortMessage || successMessage : successMessage;
  const restartLabel = textValue(project.cta_restart);

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-xl flex-col items-center justify-center px-10 pb-10 pt-8 text-center">
      {title && <h1 className="text-sm font-semibold text-slate-900">{title}</h1>}
      {message && <p className="mt-3 text-sm leading-6 text-slate-600">{message}</p>}
      {restartLabel && onRestart && (
        <button
          type="button"
          onClick={onRestart}
          className="mt-6 cursor-pointer rounded bg-[var(--accent)] px-5 py-2 text-sm font-semibold text-white transition"
        >
          {restartLabel}
        </button>
      )}
    </div>
  );
}
