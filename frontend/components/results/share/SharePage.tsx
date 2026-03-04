"use client";

import * as React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  shareGetSession,
  shareInfo,
  shareListSessions,
  shareLogin,
  shareUpdateSessionAnnotation,
  type SessionListItem,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Avatar } from "@/components/ui/avatar";
import { Skeleton, SkeletonMessage } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { FilterBar } from "@/components/results/shared/FilterBar";
import { SessionList } from "@/components/results/shared/SessionList";
import { TranscriptView } from "@/components/results/shared/TranscriptView";
import {
  toLocalDateKey, groupByDay, formatTokenCount,
  formatLocalTime, buildTranscriptItems,
  type TranscriptItem,
} from "@/lib/format";
import type { BaseFilterField, FilterRow, TextFilterOp, DateFilterOp, ResponsesFilterOp, AudioFilterOp } from "@/lib/session-filters";

type FilterField = BaseFilterField;
type ShareFilterRow = FilterRow<FilterField>;

export function SharePage() {
  const params = useParams();
  const tokenParam = params?.token;
  const token = Array.isArray(tokenParam) ? tokenParam[0] : tokenParam || "";

  const infoQ = useQuery({
    queryKey: ["share", "info", token],
    queryFn: () => shareInfo(token),
    retry: false,
  });

  const [password, setPassword] = React.useState("");
  const [authed, setAuthed] = React.useState(false);

  const loginM = useMutation({
    mutationFn: () => shareLogin(token, password),
    onSuccess: () => setAuthed(true),
  });

  const toDateInputValue = React.useCallback((date: Date) => {
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 10);
  }, []);

  const resolveDateRange = React.useCallback(
    (row?: FilterRow) => {
      if (!row) return { from: "", to: "" };
      const op = row.op as DateFilterOp;
      const today = new Date();
      const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
      if (op === "after" && row.value) return { from: row.value, to: "" };
      if (op === "before" && row.value) return { from: "", to: row.value };
      if (op === "between" && row.value && row.value2) return { from: row.value, to: row.value2 };
      if (op === "last_7_days") {
        const from = new Date(startOfToday);
        from.setDate(from.getDate() - 6);
        return { from: toDateInputValue(from), to: toDateInputValue(startOfToday) };
      }
      if (op === "last_30_days") {
        const from = new Date(startOfToday);
        from.setDate(from.getDate() - 29);
        return { from: toDateInputValue(from), to: toDateInputValue(startOfToday) };
      }
      if (op === "this_week") {
        const day = startOfToday.getDay();
        const diff = (day + 6) % 7;
        const from = new Date(startOfToday);
        from.setDate(from.getDate() - diff);
        return { from: toDateInputValue(from), to: toDateInputValue(startOfToday) };
      }
      if (op === "this_month") {
        const from = new Date(startOfToday.getFullYear(), startOfToday.getMonth(), 1);
        return { from: toDateInputValue(from), to: toDateInputValue(startOfToday) };
      }
      return { from: "", to: "" };
    },
    [toDateInputValue]
  );

  const resolveResponsesRange = React.useCallback((row?: FilterRow) => {
    if (!row) return { min: "", max: "" };
    const op = row.op as ResponsesFilterOp;
    const val = row.value.trim();
    const val2 = (row.value2 || "").trim();
    if (op === "equals" && val) return { min: val, max: val };
    if (op === "at_least" && val) return { min: val, max: "" };
    if (op === "at_most" && val) return { min: "", max: val };
    if (op === "between" && val && val2) return { min: val, max: val2 };
    return { min: "", max: "" };
  }, []);

  const resolveAudioRange = React.useCallback((row?: FilterRow) => {
    if (!row) return { min: "", max: "" };
    const op = row.op as AudioFilterOp;
    const val = row.value.trim();
    const val2 = (row.value2 || "").trim();
    if (op === "has") return { min: "1", max: "" };
    if (op === "not_has") return { min: "", max: "0" };
    if (op === "at_least" && val) return { min: val, max: "" };
    if (op === "at_most" && val) return { min: "", max: val };
    if (op === "between" && val && val2) return { min: val, max: val2 };
    return { min: "", max: "" };
  }, []);

  // Viewer state
  const [search, setSearch] = React.useState("");
  const [sortKey, setSortKey] = React.useState("latest");
  const [showAudioOnly, setShowAudioOnly] = React.useState(false);
  const [hideEmptyInterviews, setHideEmptyInterviews] = React.useState(false);
  const [hideSessionsMarkedAsSeen, setHideSessionsMarkedAsSeen] = React.useState(false);
  const [filterRows, setFilterRows] = React.useState<ShareFilterRow[]>([
    { id: "external_id", field: "external_id", op: "contains", value: "" },
  ]);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [noteDraft, setNoteDraft] = React.useState("");
  const [noteStatus, setNoteStatus] = React.useState<"idle" | "saving" | "saved" | "error">("idle");
  const noteSaveTimer = React.useRef<number | null>(null);
  const [hasMounted, setHasMounted] = React.useState(false);

  const copyText = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      return false;
    }
  };
  const noteDraftRef = React.useRef("");
  const lastSavedRef = React.useRef("");
  const hideEmptyStorageKey = React.useMemo(
    () => `qvantify:share:${token}:hide-empty-interviews`,
    [token]
  );
  const userTimeZone = React.useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "",
    []
  );
  React.useEffect(() => {
    setHasMounted(true);
  }, []);
  React.useEffect(() => {
    try {
      const stored = window.localStorage.getItem(hideEmptyStorageKey);
      if (stored === "1") {
        setHideEmptyInterviews(true);
      } else {
        setHideEmptyInterviews(false);
      }
    } catch {
      // Ignore localStorage failures in restricted browser contexts.
    }
  }, [hideEmptyStorageKey]);
  React.useEffect(() => {
    try {
      window.localStorage.setItem(hideEmptyStorageKey, hideEmptyInterviews ? "1" : "0");
    } catch {
      // Ignore localStorage failures in restricted browser contexts.
    }
  }, [hideEmptyInterviews, hideEmptyStorageKey]);
  const fmtTime = React.useCallback(
    (value?: string | null) => formatLocalTime(value, userTimeZone),
    [userTimeZone]
  );
  const formatSidebarDateTime = React.useCallback(
    (value?: string | null) => {
      if (!value) return "";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return "";
      const options: Intl.DateTimeFormatOptions = {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      };
      if (userTimeZone) options.timeZone = userTimeZone;
      const parts = new Intl.DateTimeFormat("en-GB", options).formatToParts(date);
      const lookup: Record<string, string> = {};
      for (const part of parts) {
        lookup[part.type] = part.value;
      }
      const day = lookup.day;
      const month = lookup.month?.toLowerCase();
      const year = lookup.year;
      const hour = lookup.hour;
      const minute = lookup.minute;
      if (!day || !month || !year || !hour || !minute) {
        return new Intl.DateTimeFormat("en-GB", options).format(date).replace(",", "");
      }
      return `${day} ${month} ${year} ${hour}:${minute}`;
    },
    [userTimeZone]
  );
  const formatTimeAgo = React.useCallback((value?: string | null) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const diffMs = Date.now() - date.getTime();
    if (diffMs <= 0) return "just now";
    const minutes = Math.floor(diffMs / 60000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} hr ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
    const months = Math.floor(days / 30);
    if (months < 12) return `${months} mo ago`;
    const years = Math.floor(months / 12);
    return `${years} yr ago`;
  }, []);

  const sessionFilters = React.useMemo(() => {
    const byField = new Map<FilterField, FilterRow>();
    for (const row of filterRows) {
      byField.set(row.field, row);
    }
    const params: Record<string, string> = {};
    const searchTerm = search.trim();
    if (searchTerm) params.search = searchTerm;
    params.sort = sortKey;
    const textRow = byField.get("external_id");
    if (textRow) {
      const op = textRow.op as TextFilterOp;
      if (op === "exists" || op === "not_exists") {
        params.external_id_op = op;
      } else if (op && textRow.value.trim()) {
        params.external_id_op = op;
        params.external_id_val = textRow.value.trim();
      }
    }
    const dateRow = byField.get("date");
    const { from, to } = resolveDateRange(dateRow);
    if (from) params.from = from;
    if (to) params.to = to;
    const responsesRow = byField.get("responses");
    const { min, max } = resolveResponsesRange(responsesRow);
    if (min) params.responses_min = min;
    if (max) params.responses_max = max;
    if (hideEmptyInterviews) {
      const minResponses = Number.parseInt(params.responses_min || "", 10);
      if (!Number.isFinite(minResponses) || minResponses < 1) {
        params.responses_min = "1";
      }
    }
    if (hideSessionsMarkedAsSeen) {
      params.hide_seen = "1";
    }

    const audioRow = byField.get("audio_tokens");
    const audioRange = resolveAudioRange(audioRow);
    if (audioRange.min) params.audio_min = audioRange.min;
    if (audioRange.max) params.audio_max = audioRange.max;
    return params;
  }, [
    filterRows,
    hideEmptyInterviews,
    hideSessionsMarkedAsSeen,
    resolveAudioRange,
    resolveDateRange,
    resolveResponsesRange,
    search,
    sortKey,
  ]);

  const listQ = useQuery({
    queryKey: ["share", "sessions", token, { ...sessionFilters, authed }],
    queryFn: () =>
      shareListSessions(token, {
        limit: 200,
        offset: 0,
        ...sessionFilters,
      }),
    enabled: authed,
  });

  const detailQ = useQuery({
    queryKey: ["share", "session", token, selectedId],
    queryFn: () => shareGetSession(token, selectedId!),
    enabled: authed && !!selectedId,
  });

  const likeSave = useMutation({
    mutationFn: (vars: { id: string; admin_like: -1 | 0 | 1 }) =>
      shareUpdateSessionAnnotation(token, vars.id, { admin_like: vars.admin_like }),
    onSuccess: async () => {
      await listQ.refetch();
      await detailQ.refetch();
    },
  });

  const noteSave = useMutation({
    mutationFn: (vars: { id: string; admin_note: string }) =>
      shareUpdateSessionAnnotation(token, vars.id, { admin_note: vars.admin_note }),
    onMutate: () => {
      setNoteStatus("saving");
    },
    onSuccess: async () => {
      lastSavedRef.current = noteDraftRef.current;
      setNoteStatus("saved");
      window.setTimeout(() => setNoteStatus("idle"), 1500);
      await listQ.refetch();
      await detailQ.refetch();
    },
    onError: () => setNoteStatus("error"),
  });
  const seenSave = useMutation({
    mutationFn: (vars: { id: string; is_seen: boolean }) =>
      shareUpdateSessionAnnotation(token, vars.id, { is_seen: vars.is_seen }),
    onSuccess: async () => {
      await listQ.refetch();
      await detailQ.refetch();
    },
  });

  React.useEffect(() => {
    const nextSessions = listQ.data?.sessions;
    if (!nextSessions) return;
    if (nextSessions.length === 0) {
      setSelectedId(null);
      setNoteStatus("idle");
      return;
    }
    if (!selectedId || !nextSessions.some((session) => session.id === selectedId)) {
      setSelectedId(nextSessions[0].id);
    }
  }, [listQ.data?.sessions, selectedId]);

  const sessions = listQ.data?.sessions ?? [];
  const isDateSort = sortKey === "latest" || sortKey === "oldest";
  const grouped = React.useMemo(() => {
    if (!isDateSort || sessions.length === 0) return [];
    return groupByDay(sessions, sortKey === "oldest" ? "asc" : "desc");
  }, [isDateSort, sessions, sortKey]);
  const flatSessions = React.useMemo(() => (isDateSort ? [] : sessions), [isDateSort, sessions]);

  const selected = detailQ.data?.session;
  const records = detailQ.data?.records || [];
  const displayRecords = records.filter((record) => (record.content ?? "").trim().length > 0);
  const filteredRecords = React.useMemo(() => {
    if (!showAudioOnly) return displayRecords;
    const keepIds = new Set<string>();
    for (let i = 0; i < displayRecords.length; i += 1) {
      const record = displayRecords[i];
      if (record.role === "user" && record.voice_input) {
        keepIds.add(record.id);
        const prev = displayRecords[i - 1];
        if (prev) keepIds.add(prev.id);
      }
    }
    return displayRecords.filter((record) => keepIds.has(record.id));
  }, [displayRecords, showAudioOnly]);
  const hasAudioMessages = React.useMemo(
    () => displayRecords.some((record) => record.role === "user" && record.voice_input),
    [displayRecords]
  );
  React.useEffect(() => {
    if (showAudioOnly && !hasAudioMessages) {
      setShowAudioOnly(false);
    }
  }, [hasAudioMessages, showAudioOnly]);
  const transcriptItems = React.useMemo<TranscriptItem[]>(
    () => buildTranscriptItems(filteredRecords),
    [filteredRecords]
  );

  React.useEffect(() => {
    if (!selected) return;
    const initial = selected.admin_note || "";
    setNoteDraft(initial);
    noteDraftRef.current = initial;
    lastSavedRef.current = initial;
    setNoteStatus("idle");
  }, [selected?.id]);

  React.useEffect(() => {
    noteDraftRef.current = noteDraft;
  }, [noteDraft]);

  React.useEffect(() => {
    if (!selected) {
      if (noteSaveTimer.current) {
        window.clearTimeout(noteSaveTimer.current);
        noteSaveTimer.current = null;
      }
      setNoteStatus("idle");
      return;
    }
    if (noteDraft === lastSavedRef.current) return;
    if (noteSaveTimer.current) {
      window.clearTimeout(noteSaveTimer.current);
    }
    const timerId = window.setTimeout(() => {
      noteSave.mutate({ id: selected.id, admin_note: noteDraftRef.current });
    }, 700);
    noteSaveTimer.current = timerId;
    return () => {
      window.clearTimeout(timerId);
      if (noteSaveTimer.current === timerId) {
        noteSaveTimer.current = null;
      }
    };
  }, [noteDraft, selected?.id]);

  const exportHref = React.useMemo(() => {
    const qs = new URLSearchParams();
    Object.entries(sessionFilters).forEach(([key, value]) => {
      if (!value) return;
      qs.set(key, value);
    });
    qs.set("format", "csv");
    return `/api/share/${encodeURIComponent(token)}/export?${qs.toString()}`;
  }, [token, sessionFilters]);

  const sortOptions = [
    { value: "latest", label: "Latest activity" },
    { value: "oldest", label: "Oldest activity" },
    { value: "responses_desc", label: "Most responses" },
    { value: "responses_asc", label: "Fewest responses" },
    { value: "external_id_asc", label: "External ID A-Z" },
    { value: "external_id_desc", label: "External ID Z-A" },
  ];

  const fieldOptions: Array<{ value: FilterField; label: string }> = [
    { value: "external_id", label: "External ID" },
    { value: "date", label: "Date" },
    { value: "responses", label: "Responses" },
    { value: "audio_tokens", label: "Audio tokens (usage)" },
  ];

  const defaultOperatorForField = (field: FilterField) => {
    switch (field) {
      case "external_id":
        return "contains";
      case "date":
        return "after";
      case "responses":
        return "at_least";
      case "audio_tokens":
        return "has";
      default:
        return "";
    }
  };
  const hasSessions = sessions.length > 0;
  const renderSessionRow = (s: SessionListItem) => {
    const active = s.id === selectedId;
    const title = s.persona_label || "Session";
    const ts = s.last_activity_at || s.created_at;
    const dateTimeLabel = formatSidebarDateTime(ts);
    const timeAgoLabel = hasMounted ? formatTimeAgo(ts) : "";
    const snippet = search ? s.match_snippet : null;
    const noteText = (s.admin_note || "").trim();
    const notePreview = noteText ? (noteText.length > 100 ? `${noteText.slice(0, 100)}...` : noteText) : "";
    return (
      <button
        key={s.id}
        onClick={() => setSelectedId(s.id)}
        className={`
          w-full text-left rounded-2xl p-3 transition-all-base border
          ${active
            ? "bg-[var(--brand-primary)] text-white border-[var(--brand-primary)]"
            : "bg-white border-[var(--border-default)] hover:bg-[var(--bg-surface)]"
          }
        `}
      >
        <div className="flex items-start gap-3">
          <Avatar name={title} size="sm" />
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <div className={`min-w-0 text-sm font-semibold truncate ${active ? "text-white" : "text-[var(--text-secondary)]"}`}>
                {title}
              </div>
              <div className={`shrink-0 text-right text-xs ${active ? "text-white/70" : "text-[var(--text-muted)]"}`}>
                {dateTimeLabel}
              </div>
            </div>
            <div className="mt-1 flex items-center justify-between gap-2">
              <div className={`text-xs truncate ${active ? "text-white/70" : "text-[var(--text-muted)]"}`}>
                External ID: <span className="font-mono">{s.external_id || "N/A"}</span>
              </div>
              {timeAgoLabel && (
                <div className={`shrink-0 text-[11px] ${active ? "text-white/70" : "text-[var(--text-subtle)]"}`}>
                  {timeAgoLabel}
                </div>
              )}
            </div>

            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span
                className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                  active
                    ? "border-white/30 bg-white/15 text-white"
                    : "border-[var(--border-default)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]"
                }`}
              >
                {s.answer_count} responses
              </span>
              {s.audio_tokens ? (
                <span
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                    active
                      ? "border-white/30 bg-white/10 text-white"
                      : "border-[var(--border-default)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]"
                  }`}
                >
                  <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 2a3 3 0 00-3 3v7a3 3 0 006 0V5a3 3 0 00-3-3z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 10v2a7 7 0 01-14 0v-2" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 19v3" />
                  </svg>
                  {formatTokenCount(s.audio_tokens)}
                </span>
              ) : null}
              <span
                className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                  active
                    ? "border-white/30 bg-white/10 text-white"
                    : s.is_closed
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                    : "border-amber-200 bg-amber-50 text-amber-700"
                }`}
              >
                {s.is_closed ? "Closed" : "Open"}
              </span>
              {s.is_seen ? (
                <span
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                    active
                      ? "border-white/30 bg-white/10 text-white"
                      : "border-blue-200 bg-blue-50 text-blue-700"
                  }`}
                >
                  <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
                  </svg>
                  Seen
                </span>
              ) : null}
            </div>

            <div className={`mt-2 text-[11px] font-mono truncate ${active ? "text-white/60" : "text-[var(--text-subtle)]"}`} title={s.id}>
              {s.id}
            </div>
            {notePreview && (
              <div className={`mt-1 text-xs ${active ? "text-white/85" : "text-[var(--text-secondary)]"}`} title={noteText}>
                {notePreview}
              </div>
            )}
            {snippet && (
              <div className={`mt-1 text-xs truncate ${active ? "text-white/80" : "text-[var(--text-secondary)]"}`} title={snippet}>
                Matched: “{snippet}”
              </div>
            )}
            {s.admin_like !== null && s.admin_like !== undefined && (
              <span className={`mt-1 inline-flex text-xs ${s.admin_like === 1 ? "text-emerald-700" : s.admin_like === -1 ? "text-red-700" : active ? "text-white/75" : "text-[var(--text-muted)]"}`}>
                {s.admin_like === 1 ? "👍" : s.admin_like === -1 ? "👎" : "😐"}
              </span>
            )}
          </div>
        </div>
      </button>
    );
  };

  // Loading state
  if (infoQ.isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-4 h-12 w-12 rounded-2xl skeleton" />
          <Skeleton width={120} height={16} className="mx-auto" />
        </div>
      </div>
    );
  }

  // Error state
  if (infoQ.error) {
    return (
      <div className="min-h-screen flex items-center justify-center px-5">
        <div className="glass-card rounded-3xl p-8 max-w-md w-full text-center animate-scale-in">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-red-50">
            <svg className="h-8 w-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-[var(--text-primary)]">Invalid Link</h2>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            {infoQ.error instanceof Error ? infoQ.error.message : "This link is not valid or has expired."}
          </p>
        </div>
      </div>
    );
  }

  const projectName = infoQ.data?.project?.name || infoQ.data?.project?.id || "Project";

  // Login form
  if (!authed) {
    return (
      <div className="min-h-screen flex items-center justify-center px-5 py-12">
        <div className="glass-card rounded-3xl max-w-md w-full animate-scale-in">
          <div className="p-8">
            <div className="mb-6">
              <Link href={`/results/share/${token}`} aria-label="Shared results landing">
                <img
                  src="https://cdn.prod.website-files.com/64cfa0ffd93ac106369335fa/64cfa57b8416a474a5c3d68f_Qvantify.svg"
                  alt="Qvantify"
                  className="h-6 w-auto brand-logo"
                />
              </Link>
              <div className="mt-3 text-xs text-[var(--text-muted)] uppercase tracking-wide font-semibold">
                Shared Results
              </div>
              <h1 className="text-xl font-bold text-[var(--text-primary)]">{projectName}</h1>
            </div>

            <p className="text-sm text-[var(--text-secondary)] mb-6">
              Enter the password to view interview results.
            </p>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                loginM.mutate();
              }}
              className="space-y-4"
            >
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                autoFocus
              />
              <Button
                type="submit"
                disabled={loginM.isPending || !password}
                className="w-full"
                variant="gradient"
              >
                {loginM.isPending ? (
                  <>
                    <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    Verifying...
                  </>
                ) : (
                  <>
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                    View Results
                  </>
                )}
              </Button>
              {loginM.error && (
                <div className="rounded-xl bg-red-50 border border-red-200 p-3 text-sm text-red-700 animate-slide-up">
                  {(loginM.error as Error).message}
                </div>
              )}
            </form>
          </div>
        </div>
      </div>
    );
  }

  // Main view
  return (
    <div className="mx-auto max-w-7xl px-5 py-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-[var(--text-primary)]">{projectName}</h1>
            <p className="text-sm text-[var(--text-muted)] mt-1">
              <span className="font-semibold text-[var(--brand-primary)]">{listQ.data?.total ?? 0}</span> sessions available
            </p>
          </div>
          <a href={exportHref}>
            <Button variant="outline" className="rounded-full">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Export CSV
            </Button>
          </a>
        </div>
      </div>

      <div className="mb-6 rounded-3xl glass-card p-5">
        <div className="flex flex-col gap-4">
          <div>
            <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">Search</div>
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search transcripts, persona, external_id, session id..."
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-white px-3 py-1.5 text-xs text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={hideEmptyInterviews}
                onChange={(e) => setHideEmptyInterviews(e.target.checked)}
                className="rounded border-[var(--border-default)]"
              />
              Hide empty interviews
            </label>
            <label className="flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-white px-3 py-1.5 text-xs text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={hideSessionsMarkedAsSeen}
                onChange={(e) => setHideSessionsMarkedAsSeen(e.target.checked)}
                className="rounded border-[var(--border-default)]"
              />
              Hide sessions marked as seen
            </label>
          </div>

          <FilterBar
            rows={filterRows}
            onRowsChange={setFilterRows}
            fieldOptions={fieldOptions}
            defaultOperatorForField={defaultOperatorForField}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:min-h-[calc(100vh-13rem)]">
        {/* Sidebar */}
        <div className="lg:col-span-4 space-y-4 lg:flex lg:min-h-0 lg:flex-col">
          {/* Sessions */}
          <SessionList
            className="glass-card rounded-3xl overflow-hidden lg:flex lg:min-h-0 lg:flex-1 lg:flex-col"
            header={
              <>
                <div className="text-sm font-semibold text-[var(--text-primary)]">Sessions</div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--text-muted)]">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">Sort</span>
                    <div className="min-w-[180px]">
                      <Select value={sortKey} onChange={setSortKey} options={sortOptions} />
                    </div>
                  </div>
                </div>
              </>
            }
            grouped={grouped}
            flatSessions={flatSessions}
            isDateSort={isDateSort}
            hasSessions={hasSessions}
            isLoading={listQ.isLoading}
            error={listQ.error as Error | null}
            hasData={!!listQ.data}
            renderRow={renderSessionRow}
            bodyClassName="p-3 max-h-[520px] overflow-y-auto bg-[var(--bg-secondary)] lg:max-h-none lg:flex-1 lg:min-h-0"
          />
        </div>

        {/* Main Content */}
        <div className="lg:col-span-8 lg:min-h-0">
          <div className="glass-card rounded-3xl overflow-hidden min-h-[600px] lg:flex lg:min-h-0 lg:h-full lg:flex-col">
            {!selectedId && (
              <div className="h-full flex items-center justify-center p-12">
                <div className="text-center">
                  <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--bg-surface)]">
                    <svg className="h-8 w-8 text-[var(--text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                  </div>
                  <div className="text-sm text-[var(--text-muted)]">Select a session to view</div>
                </div>
              </div>
            )}

            {selectedId && detailQ.isLoading && (
              <div className="p-6 space-y-4">
                <SkeletonMessage align="left" />
                <SkeletonMessage align="right" />
                <SkeletonMessage align="left" />
              </div>
            )}

            {detailQ.error && (
              <div className="p-6 text-red-400">{(detailQ.error as Error).message}</div>
            )}

            {selected && (
              <div className="flex flex-col h-full">
                {/* Header */}
                <div className="p-6 border-b border-[var(--border-default)] bg-[var(--bg-primary)]">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-4">
                      <Avatar name={selected.persona_label} size="lg" />
                      <div>
                        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                          {selected.persona_label || "Session"}
                        </h2>
                        {typeof selected.is_closed === "boolean" && (
                          <div
                            className={`mt-1 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                              selected.is_closed
                                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                : "border-amber-200 bg-amber-50 text-amber-700"
                            }`}
                          >
                            {selected.is_closed ? "Closed" : "Open"}
                          </div>
                        )}
                        <div className="text-sm text-[var(--text-muted)]">
                          {filteredRecords.length} messages
                        </div>
                        <div className="text-xs text-[var(--text-muted)]">
                          External ID: <span className="font-mono text-[var(--text-secondary)]">{selected.external_id || "N/A"}</span>
                        </div>
                        <div className="text-[11px] text-[var(--text-muted)]">
                          Times shown in your timezone{userTimeZone ? ` (${userTimeZone})` : ""}.
                        </div>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => seenSave.mutate({ id: selected.id, is_seen: !Boolean(selected.is_seen) })}
                      disabled={seenSave.isPending}
                      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-all-base ${
                        selected.is_seen
                          ? "border-blue-200 bg-blue-50 text-blue-700"
                          : "border-[var(--border-default)] bg-white text-[var(--text-secondary)]"
                      }`}
                      aria-label={
                        seenSave.isPending
                          ? "Saving seen state"
                          : selected.is_seen
                          ? "Mark session as unseen"
                          : "Mark session as seen"
                      }
                      title={
                        seenSave.isPending
                          ? "Saving..."
                          : selected.is_seen
                          ? "Marked as seen. Click to unmark."
                          : "Mark as seen"
                      }
                    >
                      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
                      </svg>
                      {seenSave.isPending ? "Saving..." : selected.is_seen ? "Seen" : "Mark as seen"}
                    </button>
                  </div>
                  {seenSave.isError && (
                    <div className="mt-2 text-xs text-red-600">Could not update seen state. Please try again.</div>
                  )}

                  {selected.findings_summary && (
                    <div className="mt-4 rounded-2xl border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
                      <div className="text-xs font-semibold text-[var(--text-muted)] mb-2">Narrative summary</div>
                      <div className="group relative">
                        <button
                          type="button"
                          onClick={() => copyText(selected.findings_summary || "")}
                          className="absolute top-0 right-0 rounded-full border border-[var(--border-default)] bg-white px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)] opacity-0 transition-opacity group-hover:opacity-100"
                          aria-label="Copy narrative summary"
                        >
                          Copy
                        </button>
                        <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                          {selected.findings_summary}
                        </p>
                      </div>
                    </div>
                  )}

                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => likeSave.mutate({ id: selected.id, admin_like: 1 })}
                      disabled={likeSave.isPending}
                      className={`flex items-center gap-2 rounded-full px-3 py-2 text-xs font-semibold transition-all-base border ${
                        selected.admin_like === 1
                          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                          : "bg-white text-[var(--text-secondary)] border-[var(--border-default)]"
                      }`}
                    >
                      👍 Like
                    </button>
                    <button
                      onClick={() => likeSave.mutate({ id: selected.id, admin_like: 0 })}
                      disabled={likeSave.isPending}
                      className={`flex items-center gap-2 rounded-full px-3 py-2 text-xs font-semibold transition-all-base border ${
                        selected.admin_like === 0
                          ? "bg-amber-50 text-amber-700 border-amber-200"
                          : "bg-white text-[var(--text-secondary)] border-[var(--border-default)]"
                      }`}
                    >
                      😐 Neutral
                    </button>
                    <button
                      onClick={() => likeSave.mutate({ id: selected.id, admin_like: -1 })}
                      disabled={likeSave.isPending}
                      className={`flex items-center gap-2 rounded-full px-3 py-2 text-xs font-semibold transition-all-base border ${
                        selected.admin_like === -1
                          ? "bg-red-50 text-red-700 border-red-200"
                          : "bg-white text-[var(--text-secondary)] border-[var(--border-default)]"
                      }`}
                    >
                      👎 Dislike
                    </button>
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <label className="flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-white px-3 py-2 text-xs text-[var(--text-secondary)]">
                      <input
                        type="checkbox"
                        checked={showAudioOnly}
                        onChange={(e) => setShowAudioOnly(e.target.checked)}
                        className="rounded border-[var(--border-default)]"
                        disabled={!hasAudioMessages}
                      />
                      Show audio messages
                    </label>
                  </div>

                  <div className="mt-4">
                    <Textarea
                      value={noteDraft}
                      onChange={(e) => setNoteDraft(e.target.value)}
                      placeholder="Add notes..."
                      className="min-h-[60px]"
                    />
                    <div className="mt-2 flex items-center justify-between">
                      <span className="text-xs text-[var(--text-muted)]">
                        Notes save automatically •{" "}
                        {noteStatus === "saving"
                          ? "Saving..."
                          : noteStatus === "saved"
                          ? "Saved"
                          : noteStatus === "error"
                          ? "Save failed"
                          : "Idle"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Transcript */}
                <TranscriptView
                  items={transcriptItems}
                  recordCount={filteredRecords.length}
                  emptyMessage="No messages yet."
                  formatTime={fmtTime}
                  onCopy={copyText}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
