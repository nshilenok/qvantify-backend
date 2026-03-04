"use client";

import * as React from "react";
import { SkeletonSessionItem } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/format";
import type { SessionListItem } from "@/lib/api";

interface DayGroup {
  day: string;
  sessions: SessionListItem[];
}

interface SessionListProps {
  header: React.ReactNode;
  grouped: DayGroup[];
  flatSessions: SessionListItem[];
  isDateSort: boolean;
  hasSessions: boolean;
  isLoading: boolean;
  error: Error | null;
  hasData: boolean;
  renderRow: (session: SessionListItem) => React.ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function SessionList({
  header,
  grouped,
  flatSessions,
  isDateSort,
  hasSessions,
  isLoading,
  error,
  hasData,
  renderRow,
  className,
  bodyClassName,
}: SessionListProps) {
  return (
    <div className={className ?? "glass-card rounded-3xl overflow-hidden"}>
      <div className="p-4 border-b border-[var(--border-default)]">{header}</div>

      <div className={bodyClassName ?? "p-3 max-h-[520px] overflow-y-auto bg-[var(--bg-secondary)]"}>
        {isLoading && (
          <div className="space-y-2 p-2">
            <SkeletonSessionItem />
            <SkeletonSessionItem />
            <SkeletonSessionItem />
          </div>
        )}

        {error && (
          <div className="p-4 text-sm text-red-400">{error.message}</div>
        )}

        {hasData && isDateSort && grouped.length > 0 && (
          <div className="space-y-4">
            {grouped.map((g) => (
              <div key={g.day}>
                <div className="px-3 py-1.5 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                  {formatDate(g.day)}
                </div>
                <div className="space-y-1">{g.sessions.map(renderRow)}</div>
              </div>
            ))}
          </div>
        )}

        {hasData && !isDateSort && flatSessions.length > 0 && (
          <div className="space-y-1">{flatSessions.map(renderRow)}</div>
        )}

        {hasData && !hasSessions && (
          <div className="p-8 text-center text-sm text-[var(--text-muted)]">
            No sessions found
          </div>
        )}
      </div>
    </div>
  );
}
