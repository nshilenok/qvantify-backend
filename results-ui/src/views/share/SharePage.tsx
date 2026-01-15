import * as React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
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
import { Avatar, RoleAvatar } from "@/components/ui/avatar";
import { Skeleton, SkeletonSessionItem, SkeletonMessage } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

type FilterField = "external_id" | "date" | "responses";
type TextFilterOp = "" | "exists" | "not_exists" | "equals" | "not_equals" | "contains" | "not_contains";
type DateFilterOp = "after" | "before" | "between" | "last_7_days" | "last_30_days" | "this_week" | "this_month";
type ResponsesFilterOp = "at_least" | "at_most" | "between" | "equals";

interface FilterRow {
  id: string;
  field: FilterField;
  op: string;
  value: string;
  value2?: string;
}

function groupByDay(sessions: SessionListItem[], direction: "asc" | "desc" = "desc") {
  const groups: Record<string, SessionListItem[]> = {};
  for (const s of sessions) {
    const ts = s.last_activity_at || s.created_at;
    const day = ts ? new Date(ts).toISOString().slice(0, 10) : "Unknown";
    groups[day] = groups[day] || [];
    groups[day].push(s);
  }
  const days = Object.keys(groups).sort((a, b) => {
    if (direction === "asc") return a > b ? 1 : -1;
    return a < b ? 1 : -1;
  });
  return days.map((d) => ({ day: d, sessions: groups[d] }));
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const isYesterday = new Date(now.getTime() - 86400000).toDateString() === date.toDateString();
  
  if (isToday) return "Today";
  if (isYesterday) return "Yesterday";
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function SharePage() {
  const { token } = useParams({ from: "/share/$token" });

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

  // Viewer state
  const [search, setSearch] = React.useState("");
  const [sortKey, setSortKey] = React.useState("latest");
  const [filterRows, setFilterRows] = React.useState<FilterRow[]>([
    { id: "external_id", field: "external_id", op: "contains", value: "" },
  ]);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [noteDraft, setNoteDraft] = React.useState("");
  const [noteStatus, setNoteStatus] = React.useState<"idle" | "saving" | "saved" | "error">("idle");
  const noteSaveTimer = React.useRef<number | null>(null);

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
    return params;
  }, [filterRows, resolveDateRange, resolveResponsesRange, search, sortKey]);

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
    onSuccess: async () => {
      lastSavedRef.current = noteDraftRef.current;
      setNoteStatus("saved");
      window.setTimeout(() => setNoteStatus("idle"), 1500);
      await listQ.refetch();
      await detailQ.refetch();
    },
    onError: () => setNoteStatus("error"),
  });

  React.useEffect(() => {
    if (!listQ.data?.sessions?.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId) setSelectedId(listQ.data.sessions[0].id);
  }, [listQ.data, selectedId]);

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
  interface TranscriptTopicItem {
    type: "topic";
    id: string;
    label: string;
  }
  interface TranscriptMessageItem {
    type: "message";
    id: string;
    record: (typeof displayRecords)[number];
  }
  type TranscriptItem = TranscriptTopicItem | TranscriptMessageItem;
  const transcriptItems = React.useMemo<TranscriptItem[]>(() => {
    const items: TranscriptItem[] = [];
    const topicLabels = new Map<string, string>();
    let lastTopicKey = "";
    for (const record of displayRecords) {
      const topicId = String(record.topic ?? "").trim();
      const explicitLabel = String(record.topic_label ?? "").trim();
      const fallbackLabel = String(record.content ?? "").trim();
      if (topicId) {
        if (explicitLabel) {
          topicLabels.set(topicId, explicitLabel);
        } else if (!topicLabels.has(topicId) && record.role === "assistant" && fallbackLabel) {
          topicLabels.set(topicId, fallbackLabel);
        }
      }
      const resolvedLabel = explicitLabel || (topicId ? topicLabels.get(topicId) : "");
      const topicKey = topicId || resolvedLabel || "";
      if (resolvedLabel && topicKey !== lastTopicKey) {
        items.push({ type: "topic", id: `topic-${record.id}`, label: resolvedLabel });
        lastTopicKey = topicKey;
      }
      items.push({ type: "message", id: record.id, record });
    }
    return items;
  }, [displayRecords]);

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
    if (!selected) return;
    if (noteDraft === lastSavedRef.current) return;
    if (noteSaveTimer.current) {
      window.clearTimeout(noteSaveTimer.current);
    }
    setNoteStatus("saving");
    noteSaveTimer.current = window.setTimeout(() => {
      noteSave.mutate({ id: selected.id, admin_note: noteDraftRef.current });
    }, 700);
    return () => {
      if (noteSaveTimer.current) window.clearTimeout(noteSaveTimer.current);
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
  ];

  const textOperatorOptions: Array<{ value: TextFilterOp; label: string }> = [
    { value: "", label: "Any" },
    { value: "exists", label: "Exists" },
    { value: "not_exists", label: "Does not exist" },
    { value: "equals", label: "Equals" },
    { value: "not_equals", label: "Does not equal" },
    { value: "contains", label: "Contains" },
    { value: "not_contains", label: "Does not contain" },
  ];

  const dateOperatorOptions: Array<{ value: DateFilterOp; label: string }> = [
    { value: "after", label: "After" },
    { value: "before", label: "Before" },
    { value: "between", label: "Between" },
    { value: "last_7_days", label: "Last 7 days" },
    { value: "last_30_days", label: "Last 30 days" },
    { value: "this_week", label: "This week" },
    { value: "this_month", label: "This month" },
  ];

  const responsesOperatorOptions: Array<{ value: ResponsesFilterOp; label: string }> = [
    { value: "at_least", label: "At least" },
    { value: "at_most", label: "At most" },
    { value: "between", label: "Between" },
    { value: "equals", label: "Equals" },
  ];

  const createFilterId = () => `filter-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const defaultOperatorForField = (field: FilterField) => {
    switch (field) {
      case "external_id":
        return "contains";
      case "date":
        return "after";
      case "responses":
        return "at_least";
      default:
        return "";
    }
  };

  const addFilterRow = () => {
    const used = new Set(filterRows.map((row) => row.field));
    const nextField = fieldOptions.find((opt) => !used.has(opt.value))?.value;
    if (!nextField) return;
    setFilterRows((rows) =>
      rows.concat({ id: createFilterId(), field: nextField, op: defaultOperatorForField(nextField), value: "" })
    );
  };

  const removeFilterRow = (rowId: string) => {
    setFilterRows((rows) => rows.filter((row) => row.id !== rowId));
  };

  const updateFilterRow = (rowId: string, updates: Partial<FilterRow>) => {
    setFilterRows((rows) => rows.map((row) => (row.id === rowId ? { ...row, ...updates } : row)));
  };
  const usedFields = new Set(filterRows.map((row) => row.field));
  const canAddFilters = filterRows.length < fieldOptions.length;
  const hasSessions = sessions.length > 0;
  const renderSessionRow = (s: SessionListItem) => {
    const active = s.id === selectedId;
    const title = s.persona_label || "Session";
    const ts = s.last_activity_at || s.created_at;
    const snippet = search ? s.match_snippet : null;
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
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-3 min-w-0">
            <Avatar name={title} size="sm" />
            <div className="min-w-0">
              <div className={`text-sm font-semibold truncate ${active ? "text-white" : "text-[var(--text-secondary)]"}`}>
                {title}
              </div>
              <div className={`text-xs truncate ${active ? "text-white/70" : "text-[var(--text-muted)]"}`}>
                {s.answer_count} messages
              </div>
            </div>
          </div>
          <div className={`shrink-0 text-right text-xs ${active ? "text-white/70" : "text-[var(--text-muted)]"}`}>
            <div>
              {ts ? new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
            </div>
            <div
              className={`mt-1 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                active
                  ? "border-white/30 bg-white/15 text-white"
                  : "border-[var(--border-default)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]"
              }`}
            >
              {s.answer_count} responses
            </div>
            <div
              className={`mt-1 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                active
                  ? "border-white/30 bg-white/10 text-white"
                  : s.is_closed
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-amber-200 bg-amber-50 text-amber-700"
              }`}
            >
              {s.is_closed ? "Closed" : "Open"}
            </div>
          </div>
        </div>
        <div className={`mt-1 text-[11px] font-mono truncate ${active ? "text-white/60" : "text-[var(--text-subtle)]"}`} title={s.id}>
          {s.id}
        </div>
        {snippet && (
          <div className={`mt-1 text-xs truncate ${active ? "text-white/80" : "text-[var(--text-secondary)]"}`} title={snippet}>
            Matched: “{snippet}”
          </div>
        )}
        {s.admin_like !== null && s.admin_like !== undefined && (
          <div className="mt-1 ml-10">
            <span className={`text-xs ${s.admin_like === 1 ? "text-emerald-700" : s.admin_like === -1 ? "text-red-700" : "text-[var(--text-muted)]"}`}>
              {s.admin_like === 1 ? "👍" : s.admin_like === -1 ? "👎" : "😐"}
            </span>
          </div>
        )}
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
              <Link to="/share/$token" params={{ token }} aria-label="Shared results landing">
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

          <div>
            <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">Filters</div>
            <div className="mt-3 grid gap-3">
              {filterRows.map((row) => {
                const fieldOptionsForRow = fieldOptions.filter(
                  (option) => option.value === row.field || !usedFields.has(option.value)
                );
                const isTextField = row.field === "external_id";
                const isDateField = row.field === "date";
                const isResponsesField = row.field === "responses";
                const textDisabled = row.op === "" || row.op === "exists" || row.op === "not_exists";
                const dateOp = row.op as DateFilterOp;
                const responsesOp = row.op as ResponsesFilterOp;
                const showDateInputs = ["after", "before", "between"].includes(dateOp);
                const showDateRange = dateOp === "between";
                const showResponsesRange = responsesOp === "between";

                return (
                  <div key={row.id} className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-secondary)] p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="min-w-[160px] flex-1 sm:flex-none sm:w-[180px]">
                        <Select
                          value={row.field}
                          onChange={(value) => {
                            const field = value as FilterField;
                            updateFilterRow(row.id, {
                              field,
                              op: defaultOperatorForField(field),
                              value: "",
                              value2: "",
                            });
                          }}
                          options={fieldOptionsForRow}
                        />
                      </div>
                      <div className="min-w-[180px] flex-1">
                        <Select
                          value={row.op}
                          onChange={(value) => updateFilterRow(row.id, { op: value as string, value: "", value2: "" })}
                          options={
                            isTextField ? textOperatorOptions : isDateField ? dateOperatorOptions : responsesOperatorOptions
                          }
                        />
                      </div>
                      <div className="flex-1 min-w-[220px]">
                        {isTextField && (
                          <Input
                            value={row.value}
                            onChange={(e) => updateFilterRow(row.id, { value: e.target.value })}
                            placeholder="Value"
                            disabled={textDisabled}
                          />
                        )}

                        {isDateField && !showDateInputs && (
                          <div className="flex items-center text-xs text-[var(--text-muted)]">
                            Date range auto-set
                          </div>
                        )}

                        {isDateField && showDateInputs && !showDateRange && (
                          <Input
                            type="date"
                            value={row.value}
                            onChange={(e) => updateFilterRow(row.id, { value: e.target.value })}
                          />
                        )}

                        {isDateField && showDateRange && (
                          <div className="grid gap-2 sm:grid-cols-2">
                            <Input
                              type="date"
                              value={row.value}
                              onChange={(e) => updateFilterRow(row.id, { value: e.target.value })}
                              placeholder="Start date"
                            />
                            <Input
                              type="date"
                              value={row.value2 || ""}
                              onChange={(e) => updateFilterRow(row.id, { value2: e.target.value })}
                              placeholder="End date"
                            />
                          </div>
                        )}

                        {isResponsesField && !showResponsesRange && (
                          <Input
                            type="number"
                            min={0}
                            step={1}
                            inputMode="numeric"
                            value={row.value}
                            onChange={(e) => updateFilterRow(row.id, { value: e.target.value })}
                            placeholder="Value"
                          />
                        )}

                        {isResponsesField && showResponsesRange && (
                          <div className="grid gap-2 sm:grid-cols-2">
                            <Input
                              type="number"
                              min={0}
                              step={1}
                              inputMode="numeric"
                              value={row.value}
                              onChange={(e) => updateFilterRow(row.id, { value: e.target.value })}
                              placeholder="Min"
                            />
                            <Input
                              type="number"
                              min={0}
                              step={1}
                              inputMode="numeric"
                              value={row.value2 || ""}
                              onChange={(e) => updateFilterRow(row.id, { value2: e.target.value })}
                              placeholder="Max"
                            />
                          </div>
                        )}
                      </div>
                      <button
                        onClick={() => removeFilterRow(row.id)}
                        className="ml-auto text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="pt-3">
              <button
                onClick={addFilterRow}
                disabled={!canAddFilters}
                className="rounded-full border border-[var(--border-default)] bg-white px-3 py-1 text-xs font-semibold text-[var(--text-secondary)] shadow-[var(--shadow-sm)] disabled:opacity-50"
              >
                + Add filter
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Sidebar */}
        <div className="lg:col-span-4 space-y-4">
          {/* Sessions */}
          <div className="glass-card rounded-3xl overflow-hidden">
            <div className="p-4 border-b border-[var(--border-default)]">
              <div className="text-sm font-semibold text-[var(--text-primary)]">Sessions</div>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--text-muted)]">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">Sort</span>
                  <div className="min-w-[180px]">
                    <Select value={sortKey} onChange={setSortKey} options={sortOptions} />
                  </div>
                </div>
              </div>
            </div>

            <div className="p-3 max-h-[520px] overflow-y-auto bg-[var(--bg-secondary)]">
              {listQ.isLoading && (
                <div className="space-y-2 p-2">
                  <SkeletonSessionItem />
                  <SkeletonSessionItem />
                  <SkeletonSessionItem />
                </div>
              )}

              {listQ.error && (
                <div className="p-4 text-sm text-red-400">{(listQ.error as Error).message}</div>
              )}

              {listQ.data && isDateSort && grouped.length > 0 && (
                <div className="space-y-4">
                  {grouped.map((g) => (
                    <div key={g.day}>
                      <div className="px-3 py-1.5 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                        {formatDate(g.day)}
                      </div>
                      <div className="space-y-1">{g.sessions.map(renderSessionRow)}</div>
                    </div>
                  ))}
                </div>
              )}

              {listQ.data && !isDateSort && flatSessions.length > 0 && (
                <div className="space-y-1">{flatSessions.map(renderSessionRow)}</div>
              )}

              {listQ.data && !hasSessions && (
                <div className="p-8 text-center text-sm text-[var(--text-muted)]">
                  No sessions found
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="lg:col-span-8">
          <div className="glass-card rounded-3xl overflow-hidden min-h-[600px]">
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
                        {displayRecords.length} messages
                      </div>
                    </div>
                  </div>

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
                <div className="flex-1 overflow-y-auto p-6 bg-[var(--bg-secondary)]">
                  <div className="space-y-4">
                    {transcriptItems.map((item) => {
                      if (item.type === "topic") {
                        return (
                          <div key={item.id} className="flex justify-center">
                            <div className="rounded-full border border-[var(--border-default)] bg-[var(--bg-secondary)] px-3 py-1 text-xs text-[var(--text-muted)]">
                              {item.label}
                            </div>
                          </div>
                        );
                      }

                      const m = item.record;
                      const isUser = m.role === "user";

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
                                ${isUser
                                  ? "bg-[var(--brand-primary)] text-white"
                                  : "bg-white border border-[var(--border-default)] text-[var(--text-primary)]"
                                }
                              `}
                            >
                              <button
                                type="button"
                                onClick={() => copyText(m.content || "")}
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
                            <div className={`mt-1.5 text-[10px] text-[var(--text-muted)] ${isUser ? "text-right" : ""}`}>
                              {m.created_at ? new Date(m.created_at).toLocaleTimeString() : ""}
                            </div>
                          </div>
                        </div>
                      );
                    })}

                    {displayRecords.length === 0 && (
                      <div className="text-center py-12 text-sm text-[var(--text-muted)]">
                        No messages yet.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
