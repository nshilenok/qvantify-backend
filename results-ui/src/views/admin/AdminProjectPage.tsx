import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import {
  adminGetProject,
  adminGetProjectUsage,
  adminGetSession,
  adminListSessions,
  adminListShareLinks,
  adminCreateShareLink,
  adminRevokeShareLink,
  adminUpdateSessionAnnotation,
  adminDeleteSessions,
  type SessionListItem,
  type ShareLink,
} from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Avatar, RoleAvatar } from "@/components/ui/avatar";
import { SkeletonSessionItem, SkeletonMessage } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";

type FilterField = "external_id" | "note" | "rating" | "date" | "responses";
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

function formatTokenCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return `${value}`;
}

function formatUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

export function AdminProjectPage() {
  const { projectId } = useParams({ from: "/admin/projects/$projectId" });

  const [search, setSearch] = React.useState("");
  const [sortKey, setSortKey] = React.useState("latest");
  const [filterRows, setFilterRows] = React.useState<FilterRow[]>([
    { id: "external_id", field: "external_id", op: "contains", value: "" },
  ]);

  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [includeSystem, setIncludeSystem] = React.useState(false);
  const [noteDraft, setNoteDraft] = React.useState("");
  const [shareModalOpen, setShareModalOpen] = React.useState(false);
  const [exportModalOpen, setExportModalOpen] = React.useState(false);
  const [copiedLocalShareUrl, setCopiedLocalShareUrl] = React.useState(false);
  const [copiedWebShareUrl, setCopiedWebShareUrl] = React.useState(false);
  const [copiedSharePassword, setCopiedSharePassword] = React.useState(false);
  const [copiedProjectId, setCopiedProjectId] = React.useState(false);
  const [copiedParticipationLink, setCopiedParticipationLink] = React.useState(false);
  const [optimisticLike, setOptimisticLike] = React.useState<-1 | 0 | 1 | null>(null);
  const [likeStatus, setLikeStatus] = React.useState<"idle" | "saving" | "saved" | "error">("idle");
  const [likeBlinkKey, setLikeBlinkKey] = React.useState(0);
  const [noteStatus, setNoteStatus] = React.useState<"idle" | "saving" | "saved" | "error">("idle");
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());
  const [selectAllMatching, setSelectAllMatching] = React.useState(false);
  const [excludedIds, setExcludedIds] = React.useState<Set<string>>(new Set());
  const [deleteModalOpen, setDeleteModalOpen] = React.useState(false);
  const queryClient = useQueryClient();
  const noteSaveTimer = React.useRef<number | null>(null);
  const noteDraftRef = React.useRef("");
  const lastSavedRef = React.useRef("");
  const likeStatusTimer = React.useRef<number | null>(null);
  const previousLikeRef = React.useRef<-1 | 0 | 1 | null>(null);

  const projectQ = useQuery({
    queryKey: ["admin", "project", projectId],
    queryFn: () => adminGetProject(projectId),
  });

  const usageQ = useQuery({
    queryKey: ["admin", "project-usage", projectId],
    queryFn: () => adminGetProjectUsage(projectId),
  });

  const shareLinksQ = useQuery({
    queryKey: ["admin", "share-links", projectId],
    queryFn: () => adminListShareLinks(projectId),
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

  const sessionFilters = React.useMemo(() => {
    const byField = new Map<FilterField, FilterRow>();
    for (const row of filterRows) {
      byField.set(row.field, row);
    }

    const params: Record<string, string> = {};
    const searchTerm = search.trim();
    if (searchTerm) params.search = searchTerm;
    params.sort = sortKey;
    const applyTextFilter = (prefix: "external_id" | "note", row?: FilterRow) => {
      if (!row) return;
      const op = row.op as TextFilterOp;
      if (!op) return;
      if (op === "exists" || op === "not_exists") {
        params[`${prefix}_op`] = op;
        return;
      }
      const val = row.value.trim();
      if (!val) return;
      params[`${prefix}_op`] = op;
      params[`${prefix}_val`] = val;
    };

    applyTextFilter("external_id", byField.get("external_id"));
    applyTextFilter("note", byField.get("note"));

    const ratingRow = byField.get("rating");
    if (ratingRow && ["-1", "0", "1"].includes(ratingRow.value)) {
      params.like = ratingRow.value;
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
    queryKey: ["admin", "sessions", projectId, sessionFilters],
    queryFn: () =>
      adminListSessions(projectId, {
        limit: 200,
        offset: 0,
        ...sessionFilters,
      }),
  });

  const usageTotals = usageQ.data?.totals;
  const usageTotalsUsd = usageQ.data?.totals_usd;
  const usdRate = usageQ.data?.rate_usd_per_1k ?? 0.01;
  const totalTokens = usageTotals?.total ?? 0;
  const interviewTokens = usageTotals?.interviews ?? 0;
  const summaryTokens = usageTotals?.summary ?? 0;
  const otherTokens = usageTotals?.other ?? 0;
  const totalUsd =
    usageTotalsUsd?.total ?? (totalTokens / 1000) * usdRate;
  const interviewUsd =
    usageTotalsUsd?.interviews ?? (interviewTokens / 1000) * usdRate;
  const summaryUsd =
    usageTotalsUsd?.summary ?? (summaryTokens / 1000) * usdRate;
  const hasUsage = totalTokens > 0;
  const interviewPct = totalTokens > 0 ? (interviewTokens / totalTokens) * 100 : 0;
  const summaryPct = totalTokens > 0 ? (summaryTokens / totalTokens) * 100 : 0;
  const otherPct = totalTokens > 0 ? (otherTokens / totalTokens) * 100 : 0;

  const detailQ = useQuery({
    queryKey: ["admin", "session", projectId, selectedId, includeSystem],
    queryFn: () => adminGetSession(projectId, selectedId!, includeSystem),
    enabled: !!selectedId,
  });

  const allSessionsQ = useQuery({
    queryKey: ["admin", "sessions-total", projectId],
    queryFn: () =>
      adminListSessions(projectId, {
        limit: 1,
        offset: 0,
      }),
  });

  React.useEffect(() => {
    setSelectedIds(new Set());
    setExcludedIds(new Set());
    setSelectAllMatching(false);
  }, [sessionFilters]);

  React.useEffect(() => {
    if (!listQ.data?.sessions?.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId) {
      setSelectedId(listQ.data.sessions[0].id);
      return;
    }
    const stillVisible = listQ.data.sessions.some((s) => s.id === selectedId);
    if (!stillVisible) setSelectedId(listQ.data.sessions[0].id);
  }, [listQ.data, selectedId]);

  const likeSave = useMutation({
    mutationFn: (vars: { id: string; admin_like: -1 | 0 | 1 }) =>
      adminUpdateSessionAnnotation(projectId, vars.id, { admin_like: vars.admin_like }),
    onSuccess: async () => {
      setLikeStatus("saved");
      setLikeBlinkKey((key) => key + 1);
      if (likeStatusTimer.current) window.clearTimeout(likeStatusTimer.current);
      likeStatusTimer.current = window.setTimeout(() => setLikeStatus("idle"), 1500);
      await listQ.refetch();
      await detailQ.refetch();
    },
    onError: () => {
      setOptimisticLike(previousLikeRef.current ?? null);
      setLikeStatus("error");
      if (likeStatusTimer.current) window.clearTimeout(likeStatusTimer.current);
      likeStatusTimer.current = window.setTimeout(() => setLikeStatus("idle"), 2000);
    },
  });

  const noteSave = useMutation({
    mutationFn: (vars: { id: string; admin_note: string }) =>
      adminUpdateSessionAnnotation(projectId, vars.id, { admin_note: vars.admin_note }),
    onSuccess: async () => {
      lastSavedRef.current = noteDraftRef.current;
      setNoteStatus("saved");
      window.setTimeout(() => setNoteStatus("idle"), 1500);
      await listQ.refetch();
      await detailQ.refetch();
    },
    onError: () => setNoteStatus("error"),
  });

  const deleteSessionsM = useMutation({
    mutationFn: (payload: {
      ids?: string[];
      select_all?: boolean;
      exclude_ids?: string[];
      filters?: Record<string, string>;
    }) => adminDeleteSessions(projectId, payload),
    onSuccess: async () => {
      setSelectedIds(new Set());
      setExcludedIds(new Set());
      setSelectAllMatching(false);
      setSelectedId(null);
      setDeleteModalOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["admin", "sessions", projectId] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "session", projectId] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "sessions-total", projectId] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "project", projectId] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "projects"] });
    },
  });

  const selected = detailQ.data?.session;
  const records = detailQ.data?.records || [];
  const displayRecords = records.filter((record) => (record.content ?? "").trim().length > 0);
  const displaySessions = React.useMemo(() => {
    if (!listQ.data?.sessions) return [];
    if (!selectedId || optimisticLike === null) return listQ.data.sessions;
    return listQ.data.sessions.map((session) =>
      session.id === selectedId ? { ...session, admin_like: optimisticLike } : session
    );
  }, [listQ.data?.sessions, selectedId, optimisticLike]);
  const isDateSort = sortKey === "latest" || sortKey === "oldest";
  const grouped = React.useMemo(() => {
    if (!isDateSort || !displaySessions.length) return [];
    return groupByDay(displaySessions, sortKey === "oldest" ? "asc" : "desc");
  }, [displaySessions, isDateSort, sortKey]);
  const flatSessions = React.useMemo(() => (isDateSort ? [] : displaySessions), [displaySessions, isDateSort]);
  const projectDetails = projectQ.data?.project;
  const isSessionSelected = React.useCallback(
    (sessionId: string) =>
      selectAllMatching ? !excludedIds.has(sessionId) : selectedIds.has(sessionId),
    [excludedIds, selectAllMatching, selectedIds]
  );
  const selectedCount = React.useMemo(() => {
    if (selectAllMatching) {
      const total = listQ.data?.total ?? 0;
      return Math.max(0, total - excludedIds.size);
    }
    return selectedIds.size;
  }, [excludedIds.size, listQ.data?.total, selectAllMatching, selectedIds.size]);

  const toggleSessionSelection = (sessionId: string) => {
    if (selectAllMatching) {
      setExcludedIds((prev) => {
        const next = new Set(prev);
        if (next.has(sessionId)) {
          next.delete(sessionId);
        } else {
          next.add(sessionId);
        }
        return next;
      });
      return;
    }
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(sessionId)) {
        next.delete(sessionId);
      } else {
        next.add(sessionId);
      }
      return next;
    });
  };

  const toggleSelectAllMatching = (checked: boolean) => {
    setSelectAllMatching(checked);
    setExcludedIds(new Set());
    setSelectedIds(new Set());
  };

  const projectFields = React.useMemo(() => {
    if (!projectDetails) return [];
    return [
      { key: "default_prompt", label: "Default prompt", value: projectDetails.default_prompt },
      { key: "id", label: "Project ID", value: projectDetails.id },
      { key: "name", label: "Name", value: projectDetails.name },
      { key: "logo", label: "Logo URL", value: projectDetails.logo },
      { key: "colour", label: "Brand color", value: projectDetails.colour },
      { key: "welcome_title", label: "Welcome title", value: projectDetails.welcome_title },
      { key: "welcome_message", label: "Welcome message", value: projectDetails.welcome_message },
      { key: "welcome_second_title", label: "Welcome second title", value: projectDetails.welcome_second_title },
      { key: "welcome_second_message", label: "Welcome second message", value: projectDetails.welcome_second_message },
      { key: "success_title", label: "Success title", value: projectDetails.success_title },
      { key: "success_message", label: "Success message", value: projectDetails.success_message },
      { key: "abort_title", label: "Abort title", value: projectDetails.abort_title },
      { key: "abort_message", label: "Abort message", value: projectDetails.abort_message },
      { key: "consent", label: "Consent copy", value: projectDetails.consent },
      { key: "cta_next", label: "CTA next", value: projectDetails.cta_next },
      { key: "cta_reply", label: "CTA reply", value: projectDetails.cta_reply },
      { key: "cta_abort", label: "CTA abort", value: projectDetails.cta_abort },
      { key: "cta_restart", label: "CTA restart", value: projectDetails.cta_restart },
      { key: "question_title", label: "Question title", value: projectDetails.question_title },
      { key: "answer_title", label: "Answer title", value: projectDetails.answer_title },
      { key: "answer_placeholder", label: "Answer placeholder", value: projectDetails.answer_placeholder },
      { key: "loading", label: "Loading text", value: projectDetails.loading },
      { key: "collect_email", label: "Collect email", value: projectDetails.collect_email, type: "boolean" },
      { key: "email_title", label: "Email title", value: projectDetails.email_title },
      { key: "email_placeholder", label: "Email placeholder", value: projectDetails.email_placeholder },
      { key: "consent_link", label: "Consent link", value: projectDetails.consent_link },
      { key: "skip_welcome", label: "Welcome screen", value: projectDetails.skip_welcome, type: "boolean", invert: true },
      { key: "dark_mode", label: "Dark mode", value: projectDetails.dark_mode, type: "boolean" },
      { key: "inline_consent", label: "Inline consent", value: projectDetails.inline_consent, type: "boolean" },
      { key: "model", label: "Model", value: projectDetails.model },
      { key: "temperature", label: "Temperature", value: projectDetails.temperature },
      { key: "top_p", label: "Top p", value: projectDetails.top_p },
      { key: "api", label: "API", value: projectDetails.api },
    ];
  }, [projectDetails]);

  React.useEffect(() => {
    if (!selected) return;
    setOptimisticLike(selected.admin_like ?? null);
    setLikeStatus("idle");
    if (likeStatusTimer.current) window.clearTimeout(likeStatusTimer.current);
    const initial = selected.admin_note || "";
    setNoteDraft(initial);
    noteDraftRef.current = initial;
    lastSavedRef.current = initial;
    setNoteStatus("idle");
  }, [selected?.id]);

  React.useEffect(() => {
    noteDraftRef.current = noteDraft;
  }, [noteDraft]);

  const currentLike = optimisticLike ?? selected?.admin_like ?? null;

  const handleLikeClick = (value: -1 | 0 | 1) => {
    if (!selected || likeSave.isPending) return;
    previousLikeRef.current = currentLike;
    setOptimisticLike(value);
    setLikeStatus("saving");
    likeSave.mutate({ id: selected.id, admin_like: value });
  };

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
    return `/api/admin/projects/${encodeURIComponent(projectId)}/export?${qs.toString()}`;
  }, [projectId, sessionFilters]);

  const exportAllHref = `/api/admin/projects/${encodeURIComponent(projectId)}/export?format=csv`;

  // Get the active share link (if any)
  const activeShareLink: ShareLink | null = React.useMemo(() => {
    const links = shareLinksQ.data?.links || [];
    return links.find((l) => l.status === "active") || null;
  }, [shareLinksQ.data]);

  const sharingEnabled = !!activeShareLink;

  const createShareM = useMutation({
    mutationFn: () => adminCreateShareLink(projectId, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "share-links", projectId] });
    },
  });

  const revokeShareM = useMutation({
    mutationFn: (linkId: string) => adminRevokeShareLink(projectId, linkId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "share-links", projectId] });
    },
  });

  const handleToggleSharing = async (enabled: boolean) => {
    if (enabled) {
      // Enable sharing - create a new link
      await createShareM.mutateAsync();
    } else {
      // Disable sharing - revoke all active links
      const activeLinks = (shareLinksQ.data?.links || []).filter((l) => l.status === "active");
      for (const link of activeLinks) {
        await revokeShareM.mutateAsync(link.id);
      }
    }
  };

  const copyText = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      return false;
    }
  };

  const handleCopyShareValue = async (
    value: string | null | undefined,
    setCopied: React.Dispatch<React.SetStateAction<boolean>>
  ) => {
    if (!value) return;
    const ok = await copyText(value);
    if (!ok) return;
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const handleCopySharePassword = async () => {
    await handleCopyShareValue(activeShareLink?.password, setCopiedSharePassword);
  };

  const defaultExternalId = "sample@user.com";
  const buildParticipationPath = React.useCallback(
    (externalId?: string | null) => {
      const params = new URLSearchParams({
        interview: projectId,
        external_id: externalId || defaultExternalId,
      });
      return `/?${params.toString()}`;
    },
    [projectId, defaultExternalId]
  );
  const buildParticipationLink = React.useCallback(
    (externalId?: string | null) => {
      const base = typeof window === "undefined" ? "" : window.location.origin;
      return `${base}${buildParticipationPath(externalId)}`;
    },
    [buildParticipationPath]
  );
  const participationLink = React.useMemo(
    () => buildParticipationLink(defaultExternalId),
    [buildParticipationLink, defaultExternalId]
  );

  const sharePath = React.useMemo(() => {
    if (activeShareLink?.share_path) return activeShareLink.share_path;
    if (!activeShareLink?.share_url) return "";
    try {
      return new URL(activeShareLink.share_url).pathname;
    } catch {
      return "";
    }
  }, [activeShareLink?.share_path, activeShareLink?.share_url]);

  const localShareUrl = React.useMemo(() => {
    if (!sharePath) return activeShareLink?.share_url || "";
    if (typeof window === "undefined") return activeShareLink?.share_url || "";
    return `${window.location.origin}${sharePath}`;
  }, [activeShareLink?.share_url, sharePath]);

  const webShareUrl = React.useMemo(() => {
    if (!sharePath) return "";
    const base = (import.meta.env.VITE_QVANTIFY_BASE_URL || "https://app.qvantify.com").replace(/\/$/, "");
    return `${base}${sharePath}`;
  }, [sharePath]);

  const handleCopyProjectId = async () => {
    const ok = await copyText(projectId);
    if (!ok) return;
    setCopiedProjectId(true);
    window.setTimeout(() => setCopiedProjectId(false), 1500);
  };

  const handleCopyParticipationLink = async () => {
    const ok = await copyText(participationLink);
    if (!ok) return;
    setCopiedParticipationLink(true);
    window.setTimeout(() => setCopiedParticipationLink(false), 1500);
  };


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
    { value: "note", label: "Note" },
    { value: "rating", label: "Rating" },
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

  const ratingOperatorOptions = [{ value: "is", label: "Is" }];
  const ratingValueOptions = [
    { value: "", label: "Any" },
    { value: "1", label: "👍 Liked" },
    { value: "0", label: "😐 Neutral" },
    { value: "-1", label: "👎 Disliked" },
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
      case "note":
        return "contains";
      case "rating":
        return "is";
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
    setFilterRows((rows) =>
      rows.map((row) => (row.id === rowId ? { ...row, ...updates } : row))
    );
  };

  const formatValue = (value: unknown) => {
    if (value === null || value === undefined || value === "") return "—";
    return String(value);
  };

  const formatBoolean = (value: boolean | null | undefined, invert = false) => {
    if (value === null || value === undefined) {
      return { label: "—", className: "bg-zinc-100 text-[#111827]" };
    }
    const on = invert ? !value : value;
    return on
      ? { label: "On", className: "bg-emerald-50 text-emerald-700" }
      : { label: "Off", className: "bg-zinc-100 text-[#111827]" };
  };
  const usedFields = new Set(filterRows.map((row) => row.field));
  const canAddFilters = filterRows.length < fieldOptions.length;
  const deleteButtonLabel =
    selectedCount > 0 ? `Delete ${selectedCount} selected interviews` : "Delete selected interviews";
  const hasSessions = displaySessions.length > 0;
  const renderSessionRow = (s: SessionListItem) => {
    const active = s.id === selectedId;
    const title = s.persona_label || "Unnamed";
    const ts = s.last_activity_at || s.created_at;
    const snippet = search ? s.match_snippet : null;
    const isSelected = isSessionSelected(s.id);
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
            <input
              type="checkbox"
              checked={isSelected}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => {
                e.stopPropagation();
                toggleSessionSelection(s.id);
              }}
              className="rounded border-[var(--border-default)]"
            />
            <Avatar name={title} size="sm" />
            <div className="min-w-0">
              <div className={`text-sm font-semibold truncate ${active ? "text-white" : "text-[var(--text-secondary)]"}`}>
                {title}
              </div>
              <div className={`text-xs truncate ${active ? "text-white/70" : "text-[var(--text-muted)]"}`}>
                {s.external_id || "No external_id"}
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

  return (
    <div className="mx-auto max-w-7xl px-5 py-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 text-sm mb-2">
          <Link
            to="/admin"
            className="flex items-center gap-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Projects
          </Link>
          <span className="text-[var(--text-subtle)]">/</span>
          <span className="text-[var(--text-secondary)] truncate max-w-[200px]">
            {projectQ.data?.project?.name || projectId}
          </span>
        </div>

        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-[var(--text-primary)]">
              {projectQ.data?.project?.name || "Project Results"}
            </h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              <span className="font-semibold text-[var(--brand-primary)]">{listQ.data?.total ?? 0}</span> sessions match current filters
            </p>
            {projectDetails && (
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Model: <span className="font-semibold text-[var(--text-secondary)]">{formatValue(projectDetails.model)}</span>
                {" · "}
                API: <span className="font-semibold text-[var(--text-secondary)]">{formatValue(projectDetails.api)}</span>
              </p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
              <span className="rounded-full border border-[var(--border-default)] bg-white px-3 py-1">
                Project ID: <code className="font-mono">{projectId}</code>
              </span>
              <button
                onClick={handleCopyProjectId}
                className="rounded-full border border-[var(--border-default)] bg-white px-2.5 py-1 text-[11px] font-semibold text-[var(--brand-primary)] shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)]"
              >
                {copiedProjectId ? "Copied" : "Copy ID"}
              </button>
              <span className="rounded-full border border-[var(--border-default)] bg-white px-3 py-1 max-w-full">
                Participation link:{" "}
                <code
                  className="font-mono truncate inline-block max-w-[220px] sm:max-w-[360px] align-bottom"
                  title={participationLink}
                >
                  {participationLink}
                </code>
              </span>
              <button
                onClick={handleCopyParticipationLink}
                className="rounded-full border border-[var(--border-default)] bg-white px-2.5 py-1 text-[11px] font-semibold text-[var(--brand-primary)] shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)]"
              >
                {copiedParticipationLink ? "Copied" : "Copy link"}
              </button>
              <span className="text-[var(--text-subtle)]">external_id: {defaultExternalId}</span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setDeleteModalOpen(true)}
              disabled={selectedCount === 0 || deleteSessionsM.isPending}
              className="flex items-center gap-2 rounded-full border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-700 shadow-[var(--shadow-sm)] hover:bg-red-100 disabled:opacity-50"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 7h12m-1 0l-1 12a2 2 0 01-2 2H8a2 2 0 01-2-2L5 7m3-3h4a2 2 0 012 2v1H6V6a2 2 0 012-2z" />
              </svg>
              {deleteButtonLabel}
            </button>
            <button
              onClick={() => setShareModalOpen(true)}
              className="flex items-center gap-2 rounded-full bg-[var(--brand-primary)] px-4 py-2 text-sm font-semibold text-white shadow-[var(--shadow-lg)]"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
              </svg>
              Share
            </button>
            <button
              onClick={() => setExportModalOpen(true)}
              className="flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-white px-4 py-2 text-sm font-semibold text-[var(--text-secondary)] shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)]"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Export
            </button>
            <button
              onClick={() => listQ.refetch()}
              disabled={listQ.isFetching}
              className="flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-white px-4 py-2 text-sm font-semibold text-[var(--text-secondary)] shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)] disabled:opacity-50"
            >
              <svg className={`h-4 w-4 ${listQ.isFetching ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Token Usage */}
      <div className="mb-6 glass-card rounded-3xl p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
              Token usage
            </div>
            <div className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">
              {usageQ.isLoading || usageQ.error ? "—" : formatTokenCount(totalTokens)}
            </div>
            <div className="text-xs text-[var(--text-muted)]">
              {usageQ.isLoading
                ? "Loading usage..."
                : usageQ.error
                ? "Usage stats unavailable"
                : "Total tokens"}
            </div>
            {!usageQ.isLoading && !usageQ.error && (
              <div className="mt-2 text-xs text-[var(--text-muted)]">
                Est. cost:{" "}
                <span className="font-semibold text-[var(--text-secondary)]">
                  {formatUsd(totalUsd)}
                </span>{" "}
                <span className="text-[10px]">(rate {formatUsd(usdRate)} / 1k)</span>
              </div>
            )}
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--bg-secondary)] px-3 py-2 text-xs text-[var(--text-secondary)]">
              <span className="h-2 w-2 rounded-full bg-[var(--brand-primary)]" />
              <span>Interviews</span>
              <span className="font-semibold text-[var(--text-primary)]">
                {usageQ.isLoading || usageQ.error
                  ? "—"
                  : `${formatTokenCount(interviewTokens)} • ${formatUsd(interviewUsd)}`}
              </span>
            </div>
            <div className="flex items-center gap-2 rounded-xl border border-[var(--border-default)] bg-[var(--bg-secondary)] px-3 py-2 text-xs text-[var(--text-secondary)]">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              <span>Summary</span>
              <span className="font-semibold text-[var(--text-primary)]">
                {usageQ.isLoading || usageQ.error
                  ? "—"
                  : `${formatTokenCount(summaryTokens)} • ${formatUsd(summaryUsd)}`}
              </span>
            </div>
          </div>
        </div>

        <div className="mt-4">
          {usageQ.isLoading && (
            <div className="flex items-center gap-3 text-xs text-[var(--text-muted)]">
              <div className="h-2 w-full rounded-full bg-[var(--bg-secondary)] animate-pulse" />
              <span>Loading chart</span>
            </div>
          )}
          {usageQ.error && (
            <div className="text-xs text-red-500">Usage chart unavailable.</div>
          )}
          {!usageQ.isLoading && !usageQ.error && (
            <>
              <div className="flex h-2 w-full overflow-hidden rounded-full bg-[var(--bg-secondary)]">
                <div
                  className="h-full bg-[var(--brand-primary)]"
                  style={{ width: `${interviewPct}%` }}
                />
                <div
                  className="h-full bg-emerald-500"
                  style={{ width: `${summaryPct}%` }}
                />
                {otherTokens > 0 && (
                  <div
                    className="h-full bg-[var(--border-default)]"
                    style={{ width: `${otherPct}%` }}
                  />
                )}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-[var(--text-muted)]">
                <span>Interviews {Math.round(interviewPct)}%</span>
                <span>Summary {Math.round(summaryPct)}%</span>
                {otherTokens > 0 && <span>Other {Math.round(otherPct)}%</span>}
              </div>
              {!hasUsage && (
                <div className="mt-2 text-xs text-[var(--text-muted)]">
                  No token usage recorded for this project yet.
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Share Modal */}
      <Dialog open={shareModalOpen} onOpenChange={setShareModalOpen}>
        <DialogContent className="bg-[var(--bg-primary)] border border-[var(--border-default)]">
          <DialogHeader>
            <DialogTitle className="text-[var(--text-primary)]">Share Results</DialogTitle>
            <DialogDescription className="text-[var(--text-muted)]">
              Share project results with external stakeholders via a secure link and password.
            </DialogDescription>
          </DialogHeader>

          <div className="mt-4">
            {/* Enable/Disable Toggle */}
            <div className="flex items-center justify-between rounded-xl bg-[var(--bg-secondary)] border border-[var(--border-default)] p-4">
              <div>
                <div className="text-sm font-medium text-[var(--text-primary)]">Enable sharing</div>
                <div className="text-xs text-[var(--text-muted)]">
                  {sharingEnabled
                    ? "Anyone with the link and password can view results"
                    : "Generate a secure link to share results"}
                </div>
              </div>
              <Switch
                checked={sharingEnabled}
                onCheckedChange={handleToggleSharing}
                disabled={createShareM.isPending || revokeShareM.isPending}
              />
            </div>

            {/* Error display */}
            {(createShareM.error || shareLinksQ.error) && (
              <div className="mt-3 rounded-xl bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                {(createShareM.error as Error)?.message || (shareLinksQ.error as Error)?.message}
              </div>
            )}

            {/* Share Details (when enabled) */}
            {sharingEnabled && activeShareLink && (
              <div className="mt-4 space-y-4">
                <div className="rounded-xl bg-[var(--bg-secondary)] border border-[var(--border-default)] p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                      Active
                    </span>
                    <span className="text-xs text-[var(--text-muted)]">
                      Created {activeShareLink.created_at ? new Date(activeShareLink.created_at).toLocaleString() : "—"}
                    </span>
                  </div>

                  <div className="space-y-4">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-[var(--text-muted)]">Local link</label>
                      <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
                        <Input
                          readOnly
                          value={localShareUrl || "Unavailable"}
                          className="font-mono text-xs h-9"
                        />
                        <button
                          onClick={() => handleCopyShareValue(localShareUrl, setCopiedLocalShareUrl)}
                          disabled={!localShareUrl}
                          className="h-9 min-w-[110px] rounded-lg border border-[var(--border-default)] px-3 text-xs font-semibold text-[var(--text-secondary)] transition-all-base hover:bg-[var(--bg-surface)] disabled:opacity-50"
                        >
                          {copiedLocalShareUrl ? "Copied" : "Copy Local"}
                        </button>
                      </div>
                    </div>

                    <div>
                      <label className="mb-1 block text-xs font-medium text-[var(--text-muted)]">Web link</label>
                      <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
                        <Input
                          readOnly
                          value={webShareUrl || "Unavailable"}
                          className="font-mono text-xs h-9"
                        />
                        <button
                          onClick={() => handleCopyShareValue(webShareUrl, setCopiedWebShareUrl)}
                          disabled={!webShareUrl}
                          className="h-9 min-w-[110px] rounded-lg border border-[var(--border-default)] px-3 text-xs font-semibold text-[var(--text-secondary)] transition-all-base hover:bg-[var(--bg-surface)] disabled:opacity-50"
                        >
                          {copiedWebShareUrl ? "Copied" : "Copy Web"}
                        </button>
                      </div>
                    </div>

                    <div>
                      <label className="mb-1 block text-xs font-medium text-[var(--text-muted)]">Password</label>
                      <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
                        <Input
                          readOnly
                          value={activeShareLink.password || "Unavailable"}
                          className="font-mono text-xs h-9"
                        />
                        <button
                          onClick={handleCopySharePassword}
                          disabled={!activeShareLink.password}
                          className="h-9 min-w-[110px] rounded-lg border border-[var(--border-default)] px-3 text-xs font-semibold text-[var(--text-secondary)] transition-all-base hover:bg-[var(--bg-surface)] disabled:opacity-50"
                        >
                          {copiedSharePassword ? "Copied" : "Copy Password"}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Regenerate Link Option */}
                <div className="text-center">
                  <button
                    type="button"
                    className="text-xs text-[var(--text-muted)] underline hover:text-[var(--text-secondary)]"
                    onClick={async () => {
                      if (activeShareLink) {
                        await revokeShareM.mutateAsync(activeShareLink.id);
                        await createShareM.mutateAsync();
                      }
                    }}
                    disabled={createShareM.isPending || revokeShareM.isPending}
                  >
                    Regenerate link &amp; password
                  </button>
                </div>
              </div>
            )}

            {/* Loading state */}
            {(createShareM.isPending || revokeShareM.isPending) && (
              <div className="mt-4 flex items-center justify-center gap-2 text-sm text-[var(--text-muted)]">
                <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>
                </svg>
                {createShareM.isPending ? "Creating share link..." : "Updating..."}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Export Modal */}
      <Dialog open={exportModalOpen} onOpenChange={setExportModalOpen}>
        <DialogContent className="bg-[var(--bg-primary)] border border-[var(--border-default)]">
          <DialogHeader>
            <DialogTitle className="text-[var(--text-primary)]">Export Results</DialogTitle>
            <DialogDescription className="text-[var(--text-muted)]">
              Choose between exporting filtered interviews or the full project dataset.
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 space-y-3">
            <button
              onClick={() => (window.location.href = exportHref)}
              className="w-full flex items-center justify-between rounded-xl border border-[var(--border-default)] bg-[var(--bg-secondary)] px-4 py-3 text-sm font-semibold text-[var(--text-primary)] hover:bg-[var(--bg-surface)]"
            >
              <span>Export filtered interviews</span>
              <span className="text-xs text-[var(--text-muted)]">{listQ.data?.total ?? 0} sessions</span>
            </button>
            <button
              onClick={() => (window.location.href = exportAllHref)}
              className="w-full flex items-center justify-between rounded-xl border border-[var(--border-default)] bg-[var(--bg-secondary)] px-4 py-3 text-sm font-semibold text-[var(--text-primary)] hover:bg-[var(--bg-surface)]"
            >
              <span>Export all interviews</span>
              <span className="text-xs text-[var(--text-muted)]">{allSessionsQ.data?.total ?? "—"} sessions</span>
            </button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Modal */}
      <Dialog open={deleteModalOpen} onOpenChange={setDeleteModalOpen}>
        <DialogContent className="bg-[var(--bg-primary)] border border-[var(--border-default)]">
          <DialogHeader>
            <DialogTitle className="text-[var(--text-primary)]">Delete interviews</DialogTitle>
            <DialogDescription className="text-[var(--text-muted)]">
              This action permanently removes interview sessions and their transcripts.
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 space-y-3">
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              You are about to delete{" "}
              <span className="font-semibold">{selectedCount}</span>{" "}
              interview{selectedCount === 1 ? "" : "s"}. This cannot be undone.
            </div>
            {deleteSessionsM.error && (
              <div className="rounded-xl bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                {(deleteSessionsM.error as Error).message}
              </div>
            )}
            <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
              <button
                onClick={() => setDeleteModalOpen(false)}
                disabled={deleteSessionsM.isPending}
                className="rounded-full border border-[var(--border-default)] bg-white px-4 py-2 text-sm font-semibold text-[var(--text-secondary)]"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (selectedCount === 0) return;
                  if (selectAllMatching) {
                    deleteSessionsM.mutate({
                      select_all: true,
                      exclude_ids: Array.from(excludedIds),
                      filters: sessionFilters,
                    });
                    return;
                  }
                  deleteSessionsM.mutate({ ids: Array.from(selectedIds) });
                }}
                disabled={selectedCount === 0 || deleteSessionsM.isPending}
                className="rounded-full bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-[var(--shadow-sm)] disabled:opacity-50"
              >
                {deleteSessionsM.isPending ? "Deleting..." : deleteButtonLabel}
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <div className="mb-6 rounded-3xl glass-card p-5">
        <div className="flex flex-col gap-4">
          <div>
            <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">Search</div>
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search transcripts, persona, external_id, session id, notes..."
            />
          </div>
          <div>
            <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">Filters</div>
            <div className="mt-3 grid gap-3">
          {filterRows.map((row) => {
            const fieldOptionsForRow = fieldOptions.filter(
              (option) => option.value === row.field || !usedFields.has(option.value)
            );
            const isTextField = row.field === "external_id" || row.field === "note";
            const isRatingField = row.field === "rating";
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
                        isTextField
                          ? textOperatorOptions
                          : isRatingField
                          ? ratingOperatorOptions
                          : isDateField
                          ? dateOperatorOptions
                          : responsesOperatorOptions
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

                    {isRatingField && (
                      <Select
                        value={row.value}
                        onChange={(value) => updateFilterRow(row.id, { value })}
                        options={ratingValueOptions}
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
        {/* Left Sidebar */}
        <div className="lg:col-span-4 space-y-4">
          {/* Sessions List */}
          <div className="glass-card rounded-3xl overflow-hidden">
            <div className="p-4 border-b border-[var(--border-default)]">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-semibold text-[var(--text-primary)]">Sessions</div>
                <div className="text-xs text-[var(--text-muted)]">
                  {selectedCount > 0 ? `${selectedCount} selected` : "No selection"}
                </div>
              </div>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--text-muted)]">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">Sort</span>
                  <div className="min-w-[180px]">
                    <Select value={sortKey} onChange={setSortKey} options={sortOptions} />
                  </div>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--text-muted)]">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selectAllMatching}
                    onChange={(e) => toggleSelectAllMatching(e.target.checked)}
                    disabled={(listQ.data?.total ?? 0) === 0}
                    className="rounded border-[var(--border-default)]"
                  />
                  Select all {listQ.data?.total ?? 0} matching filters
                </label>
                {selectAllMatching && (
                  <span className="text-[var(--text-secondary)]">
                    Deselect any row to exclude it
                  </span>
                )}
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
                <div className="p-8 text-center">
                  <div className="text-sm text-[var(--text-muted)]">No sessions found</div>
                </div>
              )}
            </div>
          </div>
        </div>

        {projectDetails && (
          <div className="glass-card rounded-3xl p-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-[var(--text-primary)]">Project properties</div>
              <span className="text-xs text-[var(--text-muted)]">{projectFields.length} fields</span>
            </div>
            <div className="mt-4 space-y-3 max-h-[320px] overflow-y-auto pr-1">
              {projectFields.map((field) => {
                if (field.type === "boolean") {
                  const badge = formatBoolean(field.value as boolean | null | undefined, field.invert);
                  return (
                    <div key={field.key} className="flex items-start justify-between gap-3">
                      <span className="text-xs text-[var(--text-muted)]">{field.label}</span>
                      <span className={`rounded-full px-3 py-1 text-[11px] font-semibold ${badge.className}`}>
                        {badge.label}
                      </span>
                    </div>
                  );
                }
                return (
                  <div key={field.key} className="flex flex-col gap-1">
                    <span className="text-xs text-[var(--text-muted)]">{field.label}</span>
                    <span className="text-xs text-[var(--text-secondary)] break-words">
                      {formatValue(field.value)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

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
                  <div className="text-sm text-[var(--text-muted)]">Select a session to view transcript</div>
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
                {/* Session Header */}
                <div className="p-6 border-b border-[var(--border-default)] bg-[var(--bg-primary)]">
                  <div className="flex flex-col gap-4">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="flex items-start gap-4">
                        <Avatar name={selected.persona_label} size="lg" />
                        <div>
                          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                            {selected.persona_label || "Session"}
                          </h2>
                          <div className="mt-2 grid gap-1 text-xs text-[var(--text-muted)]">
                            <div>
                              Respondent ID: <code className="font-mono">{selected.id}</code>{" "}
                              <button onClick={() => copyText(selected.id)} className="text-[var(--brand-primary)]">Copy</button>
                            </div>
                            <div>
                              External ID: <code className="font-mono">{selected.external_id || "—"}</code>
                            </div>
                            <div>
                              Email: <code className="font-mono">{selected.email || "—"}</code>
                            </div>
                            <div>
                              Consent: <span className="font-medium text-[var(--text-secondary)]">{selected.consent === null || selected.consent === undefined ? "—" : selected.consent ? "Yes" : "No"}</span>
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <label className="flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-white px-3 py-2 text-xs text-[var(--text-secondary)]">
                          <input
                            type="checkbox"
                            checked={includeSystem}
                            onChange={(e) => setIncludeSystem(e.target.checked)}
                            className="rounded border-[var(--border-default)]"
                          />
                          System prompts
                        </label>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
                      <span className="rounded-full border border-[var(--border-default)] bg-white px-3 py-1">
                        Status: {selected.is_closed ? "Closed" : "Open"}
                      </span>
                      <span className="rounded-full border border-[var(--border-default)] bg-white px-3 py-1">
                        Responses: {selected.answer_count ?? 0}
                      </span>
                      <span className="rounded-full border border-[var(--border-default)] bg-white px-3 py-1">
                        Last activity: {selected.last_activity_at ? new Date(selected.last_activity_at).toLocaleString() : "—"}
                      </span>
                    </div>
                  </div>

                  {/* Findings Summary */}
                  {selected.findings_summary ? (
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
                  ) : (
                    <div className="mt-4 rounded-2xl border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4 text-sm text-[var(--text-muted)]">
                      Pending analysis. Summary will appear once the interview is processed.
                    </div>
                  )}

                  {/* Rating Buttons */}
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => handleLikeClick(1)}
                      className={`flex items-center gap-2 rounded-full px-3 py-2 text-xs font-semibold transition-all-base border ${
                        currentLike === 1
                          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                          : "bg-white text-[var(--text-secondary)] border-[var(--border-default)]"
                      }`}
                    >
                      <svg className="h-4 w-4" fill={currentLike === 1 ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
                      </svg>
                      Like
                    </button>
                    <button
                      onClick={() => handleLikeClick(0)}
                      className={`flex items-center gap-2 rounded-full px-3 py-2 text-xs font-semibold transition-all-base border ${
                        currentLike === 0
                          ? "bg-amber-50 text-amber-700 border-amber-200"
                          : "bg-white text-[var(--text-secondary)] border-[var(--border-default)]"
                      }`}
                    >
                      😐 Neutral
                    </button>
                    <button
                      onClick={() => handleLikeClick(-1)}
                      className={`flex items-center gap-2 rounded-full px-3 py-2 text-xs font-semibold transition-all-base border ${
                        currentLike === -1
                          ? "bg-red-50 text-red-700 border-red-200"
                          : "bg-white text-[var(--text-secondary)] border-[var(--border-default)]"
                      }`}
                    >
                      <svg className="h-4 w-4" fill={currentLike === -1 ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018a2 2 0 01.485.06l3.76.94m-7 10v5a2 2 0 002 2h.096c.5 0 .905-.405.905-.904 0-.715.211-1.413.608-2.008L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5" />
                      </svg>
                      Dislike
                    </button>
                    {likeStatus !== "idle" && (
                      <span
                        key={likeStatus === "saved" ? `saved-${likeBlinkKey}` : likeStatus}
                        className={`text-xs ${
                          likeStatus === "saved"
                            ? "text-emerald-600 animate-double-blink"
                            : likeStatus === "error"
                            ? "text-red-600"
                            : "text-[var(--text-muted)]"
                        }`}
                      >
                        {likeStatus === "saving"
                          ? "Saving..."
                          : likeStatus === "saved"
                          ? "Saved"
                          : "Save failed"}
                      </span>
                    )}
                  </div>

                  {/* Note */}
                  <div className="mt-4">
                    <Textarea
                      value={noteDraft}
                      onChange={(e) => setNoteDraft(e.target.value)}
                      placeholder="Add internal notes..."
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
                    {displayRecords.map((m) => {
                      const isUser = m.role === "user";
                      const isSystem = m.role === "system";

                      return (
                        <div
                          key={m.id}
                          className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""} animate-fade-in`}
                        >
                          <RoleAvatar role={m.role} size="sm" />
                          <div className={`max-w-[75%] ${isUser ? "items-end" : ""}`}>
                            <div
                              className={`
                                group relative rounded-2xl px-4 py-3 text-sm leading-relaxed
                                ${isSystem
                                  ? "bg-[var(--bg-secondary)] border border-[var(--border-default)] text-[var(--text-muted)]"
                                  : isUser
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
                            <div className={`mt-1.5 flex items-center gap-3 text-[10px] text-[var(--text-muted)] ${isUser ? "justify-end" : ""}`}>
                              <span>{m.created_at ? new Date(m.created_at).toLocaleTimeString() : ""}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}

                    {displayRecords.length === 0 && (
                      <div className="text-center py-12 text-sm text-[var(--text-muted)]">
                        No messages in this session yet.
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
