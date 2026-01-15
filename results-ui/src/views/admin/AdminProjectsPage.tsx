import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { adminListProjects } from "@/lib/api";
import { SkeletonProjectCard } from "@/components/ui/skeleton";

export function AdminProjectsPage() {
  const q = useQuery({
    queryKey: ["admin", "projects"],
    queryFn: adminListProjects,
  });

  const totalSessions = q.data?.projects?.reduce((sum, p) => sum + (p.session_count || 0), 0) ?? 0;
  const [copiedProjectId, setCopiedProjectId] = React.useState<string | null>(null);
  const testExternalId = "sample@user.com";

  const buildInterviewLink = (projectId: string) => {
    const params = new URLSearchParams({
      interview: projectId,
      external_id: testExternalId,
    });
    return `/?${params.toString()}`;
  };

  const copyInterviewLink = async (projectId: string) => {
    const base = typeof window === "undefined" ? "" : window.location.origin;
    const link = `${base}${buildInterviewLink(projectId)}`;
    try {
      await navigator.clipboard.writeText(link);
      setCopiedProjectId(projectId);
      window.setTimeout(() => setCopiedProjectId(null), 1500);
    } catch {
      setCopiedProjectId(null);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-5 py-10">
      {/* Hero Section */}
      <div className="mb-8 rounded-3xl glass-card">
        <div className="p-6 sm:p-8">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-white px-3 py-1 text-xs font-semibold text-[var(--text-secondary)]">
                Admin dashboard
              </div>
              <h1 className="mt-3 text-3xl font-semibold text-[var(--text-primary)] tracking-tight">
                Interview Projects
              </h1>
              <p className="mt-2 text-[var(--text-secondary)]">
                Browse and analyze interview results across all your projects.
              </p>
            </div>

            <div className="flex items-center gap-4">
              {/* Stats pill */}
              <div className="rounded-2xl bg-white px-5 py-3 text-center border border-[var(--border-default)] shadow-[var(--shadow-sm)]">
                <div className="text-2xl font-semibold text-[var(--text-primary)]">
                  {totalSessions}
                </div>
                <div className="text-xs text-[var(--text-muted)] font-medium">
                  Total Sessions
                </div>
              </div>

              <button
                onClick={() => q.refetch()}
                disabled={q.isFetching}
                className="flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-white px-4 py-3 text-sm font-semibold text-[var(--text-secondary)] shadow-[var(--shadow-sm)] transition-all-base hover:shadow-[var(--shadow-md)] disabled:opacity-50"
              >
                <svg
                  className={`h-4 w-4 ${q.isFetching ? "animate-spin" : ""}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                Refresh
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Loading State */}
      {q.isLoading && (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 stagger-children">
          <SkeletonProjectCard />
          <SkeletonProjectCard />
          <SkeletonProjectCard />
        </div>
      )}

      {/* Error State */}
      {q.error && (
        <div className="glass-card rounded-2xl overflow-hidden animate-slide-up">
          <div className="h-1 bg-gradient-to-r from-red-400 to-orange-400" />
          <div className="p-6">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-red-50">
                <svg className="h-6 w-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-semibold text-[var(--text-primary)]">
                  Connection Error
                </h3>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">
                  {q.error instanceof Error ? q.error.message : "Unable to load projects"}
                </p>
                <div className="mt-4 rounded-xl bg-[var(--bg-secondary)] p-4 border border-[var(--border-default)]">
                  <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">
                    Checklist
                  </div>
                  <ul className="space-y-2 text-sm text-[var(--text-secondary)]">
                    <li className="flex items-center gap-2">
                      <svg className="h-4 w-4 text-[var(--text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Server running on localhost
                    </li>
                    <li className="flex items-center gap-2">
                      <svg className="h-4 w-4 text-[var(--text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <code className="rounded bg-[var(--bg-primary)] px-1.5 py-0.5 text-xs border border-[var(--border-default)]">ADMIN_LOCAL_KEY</code> configured
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Projects Grid */}
      {q.data && (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 stagger-children">
          {q.data.projects.map((p) => (
            <Link
              key={p.id}
              to="/admin/projects/$projectId"
              params={{ projectId: p.id }}
              className="group block"
            >
              <div className="glass-card rounded-3xl overflow-hidden transition-all-slow hover:-translate-y-1 hover:shadow-[var(--shadow-lg)]">
                <div className="p-5">
                  <div className="mb-4">
                    <h3 className="text-lg font-semibold text-[var(--text-primary)] truncate transition-all">
                      {p.name || p.id}
                    </h3>
                    <p className="text-xs text-[var(--text-muted)] font-mono truncate mt-1">
                      {p.id}
                    </p>
                  </div>

                  <div className="rounded-2xl bg-[var(--bg-secondary)] p-3 border border-[var(--border-default)]">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-[var(--text-secondary)]">Sessions</span>
                      <span className="text-xl font-semibold text-[var(--text-primary)]">
                        {p.session_count}
                      </span>
                    </div>
                  </div>

                  <div className="mt-3 flex items-center justify-between text-xs">
                    <span className="text-[var(--text-muted)]">
                      {p.last_activity_at
                        ? `Last: ${new Date(p.last_activity_at).toLocaleDateString()}`
                        : "No activity"}
                    </span>
                    <span className="flex items-center gap-1 text-[var(--brand-primary)] opacity-0 group-hover:opacity-100 transition-opacity">
                      View
                      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                      </svg>
                    </span>
                  </div>

                  <div className="mt-3 flex items-center justify-between rounded-2xl border border-[var(--border-default)] bg-white px-3 py-2">
                    <span className="text-[11px] text-[var(--text-muted)] font-mono truncate">
                      {buildInterviewLink(p.id)}
                    </span>
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        copyInterviewLink(p.id);
                      }}
                      className="ml-3 shrink-0 rounded-full border border-[var(--border-default)] bg-white px-2.5 py-1 text-[11px] font-semibold text-[var(--brand-primary)] shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)]"
                    >
                      {copiedProjectId === p.id ? "Copied" : "Copy link"}
                    </button>
                  </div>
                </div>
              </div>
            </Link>
          ))}

          {/* Empty state */}
          {q.data.projects.length === 0 && (
            <div className="col-span-full">
              <div className="glass-card rounded-2xl p-12 text-center">
                <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--bg-surface)]">
                  <svg className="h-8 w-8 text-[var(--text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-[var(--text-primary)]">
                  No projects yet
                </h3>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  Projects will appear here once interviews are created.
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
