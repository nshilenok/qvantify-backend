import { describe, it, expect } from "vitest";
import {
  toLocalDateKey,
  groupByDay,
  formatDate,
  formatTokenCount,
  formatUsd,
  formatLocalTime,
  buildTranscriptItems,
  type TranscriptRecord,
} from "@/lib/format";
import type { SessionListItem } from "@/lib/results-api";

// ---------------------------------------------------------------------------
// toLocalDateKey
// ---------------------------------------------------------------------------

describe("toLocalDateKey", () => {
  it("converts ISO timestamp to YYYY-MM-DD in local time", () => {
    const result = toLocalDateKey("2026-03-04T14:30:00Z");
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('returns "Unknown" for invalid dates', () => {
    expect(toLocalDateKey("not-a-date")).toBe("Unknown");
    expect(toLocalDateKey("")).toBe("Unknown");
  });

  it("pads single-digit month and day", () => {
    const result = toLocalDateKey("2026-01-05T00:00:00Z");
    expect(result).toContain("-01-");
    expect(result).toContain("-05");
  });
});

// ---------------------------------------------------------------------------
// groupByDay
// ---------------------------------------------------------------------------

function makeSession(overrides: Partial<SessionListItem> = {}): SessionListItem {
  return {
    id: "s1",
    created_at: "2026-03-04T10:00:00Z",
    external_id: "user@test.com",
    persona_label: null,
    findings_summary: null,
    answer_count: 5,
    last_activity_at: null,
    is_closed: false,
    ...overrides,
  };
}

describe("groupByDay", () => {
  it("groups sessions by date descending by default", () => {
    const sessions = [
      makeSession({ id: "a", created_at: "2026-03-04T10:00:00Z" }),
      makeSession({ id: "b", created_at: "2026-03-03T10:00:00Z" }),
      makeSession({ id: "c", created_at: "2026-03-04T15:00:00Z" }),
    ];
    const groups = groupByDay(sessions);
    expect(groups.length).toBeGreaterThanOrEqual(2);
    expect(groups[0].day >= groups[groups.length - 1].day).toBe(true);
  });

  it("groups ascending when direction is asc", () => {
    const sessions = [
      makeSession({ id: "a", created_at: "2026-03-04T10:00:00Z" }),
      makeSession({ id: "b", created_at: "2026-03-02T10:00:00Z" }),
    ];
    const groups = groupByDay(sessions, "asc");
    expect(groups[0].day <= groups[groups.length - 1].day).toBe(true);
  });

  it("prefers last_activity_at over created_at", () => {
    const sessions = [
      makeSession({
        id: "a",
        created_at: "2026-03-01T10:00:00Z",
        last_activity_at: "2026-03-04T10:00:00Z",
      }),
    ];
    const groups = groupByDay(sessions);
    expect(groups[0].day).toContain("2026-03-04");
  });

  it('places sessions with no timestamps under "Unknown"', () => {
    const sessions = [
      makeSession({ id: "a", created_at: null, last_activity_at: null }),
    ];
    const groups = groupByDay(sessions);
    expect(groups[0].day).toBe("Unknown");
  });
});

// ---------------------------------------------------------------------------
// formatDate
// ---------------------------------------------------------------------------

describe("formatDate", () => {
  it('returns "Today" for today\'s date', () => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, "0");
    const d = String(now.getDate()).padStart(2, "0");
    expect(formatDate(`${y}-${m}-${d}`)).toBe("Today");
  });

  it('returns "Yesterday" for yesterday\'s date', () => {
    const yesterday = new Date(Date.now() - 86400000);
    const y = yesterday.getFullYear();
    const m = String(yesterday.getMonth() + 1).padStart(2, "0");
    const d = String(yesterday.getDate()).padStart(2, "0");
    expect(formatDate(`${y}-${m}-${d}`)).toBe("Yesterday");
  });

  it('returns "Mon DD" format for older dates', () => {
    const result = formatDate("2025-01-15");
    expect(result).toBe("Jan 15");
  });
});

// ---------------------------------------------------------------------------
// formatTokenCount
// ---------------------------------------------------------------------------

describe("formatTokenCount", () => {
  it("returns raw number for values < 1000", () => {
    expect(formatTokenCount(500)).toBe("500");
    expect(formatTokenCount(0)).toBe("0");
    expect(formatTokenCount(999)).toBe("999");
  });

  it('returns "Xk" for values >= 1000', () => {
    expect(formatTokenCount(1000)).toBe("1.0k");
    expect(formatTokenCount(1500)).toBe("1.5k");
    expect(formatTokenCount(99_999)).toBe("100.0k");
  });

  it('returns "XM" for values >= 1_000_000', () => {
    expect(formatTokenCount(1_000_000)).toBe("1.0M");
    expect(formatTokenCount(2_500_000)).toBe("2.5M");
  });
});

// ---------------------------------------------------------------------------
// formatUsd
// ---------------------------------------------------------------------------

describe("formatUsd", () => {
  it("formats as US currency", () => {
    const result = formatUsd(1234.5);
    expect(result).toContain("1,234.50");
    expect(result).toContain("$");
  });

  it("handles zero", () => {
    const result = formatUsd(0);
    expect(result).toContain("0.00");
  });

  it("handles small values", () => {
    const result = formatUsd(0.99);
    expect(result).toContain("0.99");
  });
});

// ---------------------------------------------------------------------------
// formatLocalTime
// ---------------------------------------------------------------------------

describe("formatLocalTime", () => {
  it("returns empty string for null/undefined", () => {
    expect(formatLocalTime(null)).toBe("");
    expect(formatLocalTime(undefined)).toBe("");
  });

  it("returns empty string for invalid date", () => {
    expect(formatLocalTime("not-a-date")).toBe("");
  });

  it("returns HH:MM formatted string for valid ISO timestamp", () => {
    const result = formatLocalTime("2026-03-04T14:30:00Z");
    expect(result).toMatch(/\d{2}:\d{2}/);
  });
});

// ---------------------------------------------------------------------------
// buildTranscriptItems
// ---------------------------------------------------------------------------

function makeRecord(overrides: Partial<TranscriptRecord> = {}): TranscriptRecord {
  return {
    id: "r1",
    created_at: "2026-03-04T14:00:00Z",
    role: "user",
    content: "Hello",
    topic: null,
    ...overrides,
  };
}

describe("buildTranscriptItems", () => {
  it("produces message items for each record", () => {
    const records = [makeRecord({ id: "r1" }), makeRecord({ id: "r2" })];
    const items = buildTranscriptItems(records);
    expect(items).toHaveLength(2);
    expect(items.every((i) => i.type === "message")).toBe(true);
  });

  it("inserts group items when topic_group changes", () => {
    const records = [
      makeRecord({ id: "r1", topic_group: "Group A" }),
      makeRecord({ id: "r2", topic_group: "Group A" }),
      makeRecord({ id: "r3", topic_group: "Group B" }),
    ];
    const items = buildTranscriptItems(records);
    const groups = items.filter((i) => i.type === "group");
    expect(groups).toHaveLength(2);
    expect(groups[0].type === "group" && groups[0].label).toBe("Group A");
    expect(groups[1].type === "group" && groups[1].label).toBe("Group B");
  });

  it("does not insert group items for empty topic_group", () => {
    const records = [makeRecord({ id: "r1", topic_group: "" })];
    const items = buildTranscriptItems(records);
    expect(items.every((i) => i.type === "message")).toBe(true);
  });

  it("returns empty array for empty input", () => {
    expect(buildTranscriptItems([])).toEqual([]);
  });
});
