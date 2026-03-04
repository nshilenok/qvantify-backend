import type { SessionListItem } from "./results-api";

// ---------------------------------------------------------------------------
// Date / number helpers
// ---------------------------------------------------------------------------

export function toLocalDateKey(ts: string): string {
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return "Unknown";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function groupByDay(
  sessions: SessionListItem[],
  direction: "asc" | "desc" = "desc"
) {
  const groups: Record<string, SessionListItem[]> = {};
  for (const s of sessions) {
    const ts = s.last_activity_at || s.created_at;
    const day = ts ? toLocalDateKey(ts) : "Unknown";
    groups[day] = groups[day] || [];
    groups[day].push(s);
  }
  const days = Object.keys(groups).sort((a, b) => {
    if (direction === "asc") return a > b ? 1 : -1;
    return a < b ? 1 : -1;
  });
  return days.map((d) => ({ day: d, sessions: groups[d] }));
}

export function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-").map(Number);
  const date =
    Number.isFinite(year) && Number.isFinite(month) && Number.isFinite(day)
      ? new Date(year, month - 1, day)
      : new Date(dateStr);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const isYesterday =
    new Date(now.getTime() - 86400000).toDateString() === date.toDateString();

  if (isToday) return "Today";
  if (isYesterday) return "Yesterday";
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function formatTokenCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return `${value}`;
}

export function formatUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatLocalTime(
  value: string | null | undefined,
  timeZone?: string | null
): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const options: Intl.DateTimeFormatOptions = {
    hour: "2-digit",
    minute: "2-digit",
  };
  if (timeZone) options.timeZone = timeZone;
  return new Intl.DateTimeFormat("en-US", options).format(date);
}

// ---------------------------------------------------------------------------
// Transcript item types & builder
// ---------------------------------------------------------------------------

export interface TranscriptRecord {
  id: string;
  created_at: string | null;
  role: "user" | "assistant" | "system";
  content: string;
  topic: string | null;
  topic_label?: string | null;
  topic_group?: string | null;
  admin_like?: number;
  admin_note?: string | null;
  voice_input?: boolean;
  audio_tokens?: number;
}

export interface TranscriptGroupItem {
  type: "group";
  id: string;
  label: string;
}

export interface TranscriptMessageItem {
  type: "message";
  id: string;
  record: TranscriptRecord;
}

export type TranscriptItem = TranscriptGroupItem | TranscriptMessageItem;

export function buildTranscriptItems(
  records: TranscriptRecord[]
): TranscriptItem[] {
  const items: TranscriptItem[] = [];
  let lastGroupKey = "";
  for (const record of records) {
    const groupLabel = String(record.topic_group ?? "").trim();
    if (groupLabel && groupLabel !== lastGroupKey) {
      items.push({
        type: "group",
        id: `group-${record.id}`,
        label: groupLabel,
      });
      lastGroupKey = groupLabel;
    }
    items.push({ type: "message", id: record.id, record });
  }
  return items;
}
