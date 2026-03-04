"use client";

import * as React from "react";
import { RoleAvatar } from "@/components/ui/avatar";
import type { TranscriptItem, TranscriptRecord } from "@/lib/format";

interface TranscriptViewProps {
  items: TranscriptItem[];
  recordCount: number;
  showSystemMessages?: boolean;
  emptyMessage?: string;
  formatTime: (value?: string | null) => string;
  onCopy: (text: string) => void;
}

export function TranscriptView({
  items,
  recordCount,
  showSystemMessages = false,
  emptyMessage = "No messages yet.",
  formatTime,
  onCopy,
}: TranscriptViewProps) {
  return (
    <div className="flex-1 overflow-y-auto p-6 bg-[var(--bg-secondary)]">
      <div className="space-y-4">
        {items.map((item) => {
          if (item.type === "group") {
            return (
              <div key={item.id} className="flex justify-center">
                <div className="text-xs text-[var(--text-muted)]">- {item.label} -</div>
              </div>
            );
          }

          const m = item.record;
          const isUser = m.role === "user";
          const isSystem = m.role === "system";
          const isVoice = isUser && m.voice_input;

          return (
            <div
              key={item.id}
              className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""} animate-fade-in`}
            >
              <RoleAvatar role={m.role} size="sm" />
              <div className={`max-w-[75%] ${isUser ? "items-end" : ""}`}>
                <div
                  className={`
                    group relative rounded-2xl px-4 py-3 text-sm leading-relaxed
                    ${showSystemMessages && isSystem
                      ? "bg-[var(--bg-secondary)] border border-[var(--border-default)] text-[var(--text-muted)]"
                      : isUser
                      ? "bg-[var(--brand-primary)] text-white"
                      : "bg-white border border-[var(--border-default)] text-[var(--text-primary)]"
                    }
                  `}
                >
                  <button
                    type="button"
                    onClick={() => onCopy(m.content || "")}
                    className={`
                      absolute top-2 ${isUser ? "left-2" : "right-2"}
                      rounded-full border border-[var(--border-default)] bg-white px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]
                      opacity-0 transition-opacity group-hover:opacity-100
                    `}
                    aria-label="Copy message"
                  >
                    Copy
                  </button>
                  <div className="whitespace-pre-wrap">{m.content}</div>
                </div>
                <div className={`mt-1.5 flex items-center gap-3 text-[10px] text-[var(--text-muted)] ${isUser ? "justify-end" : ""}`}>
                  <span>{formatTime(m.created_at)}</span>
                  {isVoice && (
                    <span className="inline-flex items-center gap-1 text-[var(--text-subtle)]">
                      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 2a3 3 0 00-3 3v7a3 3 0 006 0V5a3 3 0 00-3-3z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19 10v2a7 7 0 01-14 0v-2" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 19v3" />
                      </svg>
                      Voice
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {recordCount === 0 && (
          <div className="text-center py-12 text-sm text-[var(--text-muted)]">
            {emptyMessage}
          </div>
        )}
      </div>
    </div>
  );
}
