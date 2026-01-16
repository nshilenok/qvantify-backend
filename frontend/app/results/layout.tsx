"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import "./results.css";

export default function ResultsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [queryClient] = useState(() => new QueryClient());
  const logoTarget = pathname.startsWith("/results/share/") ? pathname : "/results/projects";

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen">
        <header className="sticky top-0 z-50 bg-[var(--bg-primary)] border-b border-[var(--border-default)]">
          <div className="mx-auto flex max-w-7xl items-center px-5 py-4">
            <Link href={logoTarget} aria-label="Results landing">
              <img
                src="https://cdn.prod.website-files.com/64cfa0ffd93ac106369335fa/64cfa57b8416a474a5c3d68f_Qvantify.svg"
                alt="Qvantify"
                className="h-6 w-auto brand-logo"
              />
            </Link>
          </div>
        </header>

        <main className="animate-fade-in">{children}</main>
      </div>
    </QueryClientProvider>
  );
}
