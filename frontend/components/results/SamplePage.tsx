"use client";

import * as React from "react";

export function SamplePage() {
  return (
    <div className="min-h-screen bg-[#f6f6f2] text-[#121416]">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <img
            src="https://cdn.prod.website-files.com/64cfa0ffd93ac106369335fa/64cfa57b8416a474a5c3d68f_Qvantify.svg"
            alt="Qvantify"
            className="h-8 w-auto"
          />
          <div className="flex items-center gap-3">
            <button className="rounded-full border border-[#e5e7eb] bg-white px-4 py-2 text-xs font-semibold text-[#111827] shadow-[0_6px_20px_rgba(15,23,42,0.08)]">
              Export summary
            </button>
            <button className="rounded-full bg-[var(--brand-primary)] px-4 py-2 text-xs font-semibold text-white shadow-[0_10px_24px_rgba(104,78,173,0.25)]">
              New share link
            </button>
          </div>
        </header>

        <section className="mt-10 grid gap-6 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
          <div>
            <h1 className="text-4xl font-semibold leading-tight text-[#0f1115]">
              Interview intelligence that feels effortless.
            </h1>
            <p className="mt-4 max-w-2xl text-base text-[#5f6670]">
              Curated transcripts, crisp insights, and instant context. Everything you need to
              understand participants at a glance.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-2 rounded-full border border-[#e5e7eb] bg-white px-4 py-2 text-xs font-semibold text-[#111827] shadow-[0_6px_16px_rgba(15,23,42,0.06)]">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              48 active sessions
            </span>
            <span className="inline-flex items-center gap-2 rounded-full border border-[#e5e7eb] bg-white px-4 py-2 text-xs font-semibold text-[#111827] shadow-[0_6px_16px_rgba(15,23,42,0.06)]">
              <span className="h-2 w-2 rounded-full bg-[var(--brand-primary)]" />
              12 waiting analysis
            </span>
          </div>
        </section>

        <section className="mt-8 rounded-3xl border border-[#e5e7eb] bg-white/80 p-6 shadow-[0_14px_30px_rgba(17,24,39,0.08)]">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex flex-1 items-center gap-3 rounded-full border border-[#e5e7eb] bg-white px-4 py-3 text-sm text-[#9ca3af] shadow-[0_6px_18px_rgba(15,23,42,0.04)]">
              <span className="text-[#111827]">Search</span>
              <span className="flex-1 text-[#9ca3af]">external_id, persona, keywords...</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {[
                "Any time",
                "Rating: All",
                "External ID: Any",
                "Notes: Any",
                "Status: Open",
              ].map((label) => (
                <button
                  key={label}
                  className="rounded-full border border-[#e5e7eb] bg-white px-4 py-2 text-xs font-semibold text-[#111827] shadow-[0_6px_14px_rgba(15,23,42,0.04)]"
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="mt-8 grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="space-y-4">
            <div className="rounded-3xl border border-[#e5e7eb] bg-white p-5 shadow-[0_16px_40px_rgba(17,24,39,0.08)]">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-[#111827]">Sessions</div>
                <span className="text-xs text-[#6b7280]">Sorted by activity</span>
              </div>
              <div className="mt-4 space-y-3">
                {[
                  {
                    name: "Growth-focused founder",
                    time: "2:14 PM",
                    external: "ext-0092",
                  },
                  {
                    name: "Ops efficiency seeker",
                    time: "1:58 PM",
                    external: "ext-0103",
                  },
                  {
                    name: "Budget-conscious leader",
                    time: "1:44 PM",
                    external: "ext-0117",
                  },
                  {
                    name: "Automation-first team",
                    time: "1:12 PM",
                    external: "ext-0129",
                  },
                ].map((item, index) => (
                  <div
                    key={item.name}
                    className={`flex items-center justify-between rounded-2xl border px-4 py-3 ${
                      index === 0
                        ? "border-[var(--brand-primary)] bg-[var(--brand-primary)] text-white"
                        : "border-[#e5e7eb] bg-[#f9fafb] text-[#111827]"
                    }`}
                  >
                    <div>
                      <div className="text-sm font-semibold">{item.name}</div>
                      <div className="mt-1 text-xs opacity-70">External ID: {item.external}</div>
                    </div>
                    <div className="text-xs opacity-70">{item.time}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-3xl border border-[#e5e7eb] bg-white p-5 shadow-[0_16px_40px_rgba(17,24,39,0.08)]">
              <div className="text-sm font-semibold text-[#111827]">Project properties</div>
              <div className="mt-4 grid gap-3 text-xs text-[#6b7280]">
                {[
                  { label: "Welcome screen", value: "On", tone: "bg-emerald-50 text-emerald-700" },
                  { label: "Collect email", value: "Off", tone: "bg-zinc-100 text-[#111827]" },
                  { label: "Dark mode", value: "Off", tone: "bg-zinc-100 text-[#111827]" },
                ].map((row) => (
                  <div key={row.label} className="flex items-center justify-between">
                    <span>{row.label}</span>
                    <span className={`rounded-full px-3 py-1 text-[11px] font-semibold ${row.tone}`}>
                      {row.value}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-3xl border border-[#e5e7eb] bg-white p-6 shadow-[0_18px_50px_rgba(17,24,39,0.1)]">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs uppercase tracking-[0.2em] text-[#9ca3af]">Selected session</div>
                <div className="mt-2 text-xl font-semibold text-[#111827]">Growth-focused founder</div>
              </div>
              <div className="flex items-center gap-2">
                <button className="rounded-full border border-[#e5e7eb] bg-white px-3 py-1.5 text-xs font-semibold text-[#111827] shadow-[0_6px_14px_rgba(15,23,42,0.04)]">
                  Copy link
                </button>
                <button className="rounded-full bg-[var(--brand-primary)] px-3 py-1.5 text-xs font-semibold text-white shadow-[0_10px_24px_rgba(104,78,173,0.25)]">
                  Highlight
                </button>
              </div>
            </div>

            <div className="mt-6 rounded-2xl border border-[#e5e7eb] bg-[#f9fafb] p-4">
              <div className="text-xs font-semibold text-[#6b7280]">Narrative summary</div>
              <p className="mt-2 text-sm text-[#111827]">
                Sees onboarding as the moment of truth and wants a calm, confident handoff. Values
                clarity over volume and expects smart follow-ups once intent is detected.
              </p>
            </div>

            <div className="mt-6 space-y-4">
              {[
                {
                  role: "Interviewer",
                  text: "What convinced you to take this call today?",
                },
                {
                  role: "Participant",
                  text: "The promise of faster handoffs. I want to spot signals quickly, not dig through noise.",
                },
                {
                  role: "Interviewer",
                  text: "Where does the current process slow you down?",
                },
              ].map((line, index) => (
                <div key={`${line.role}-${index}`} className="flex gap-3">
                  <div className="mt-1 h-8 w-8 rounded-full bg-[#111827] text-white text-[11px] flex items-center justify-center">
                    {line.role === "Participant" ? "P" : "I"}
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-[#6b7280]">{line.role}</div>
                    <div className="text-sm text-[#111827]">{line.text}</div>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-6 grid gap-3 rounded-2xl border border-[#e5e7eb] bg-white p-4">
              <div className="flex items-center justify-between text-xs text-[#6b7280]">
                <span>Auto insights</span>
                <span>Confidence: 0.82</span>
              </div>
              <div className="text-sm font-semibold text-[#111827]">Wants calm, guided onboarding</div>
              <div className="text-xs text-[#6b7280]">
                Prioritizes fast signal extraction and expects contextual follow-ups once interest is clear.
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
