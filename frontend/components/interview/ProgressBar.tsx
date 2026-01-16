import type { ProgressState } from "@/lib/types";

type ProgressBarProps = {
  progress?: ProgressState | null;
  accent?: string;
};

export default function ProgressBar({ progress, accent }: ProgressBarProps) {
  if (!progress || !progress.total) return null;
  const ratio = Number.isFinite(progress.ratio) ? progress.ratio : progress.total ? progress.current / progress.total : 0;
  const percent = Math.max(0, Math.min(1, ratio || 0));

  return (
    <div className="fixed left-0 top-0 z-50 w-full" data-testid="interview-progress">
      <div className="h-0.5 w-full bg-black/10">
        <div
          className="h-full transition-all duration-300"
          style={{ width: `${percent * 100}%`, backgroundColor: accent || "#684EAD" }}
        />
      </div>
    </div>
  );
}
