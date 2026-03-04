import { describe, it, expect } from "vitest";
import type {
  FilterRow,
  AdminFilterField,
  BaseFilterField,
  TextFilterOp,
  DateFilterOp,
  ResponsesFilterOp,
  AudioFilterOp,
} from "@/lib/session-filters";

describe("FilterRow type compliance", () => {
  it("accepts a valid admin filter row", () => {
    const row: FilterRow<AdminFilterField> = {
      id: "f1",
      field: "note",
      op: "contains",
      value: "important",
    };
    expect(row.field).toBe("note");
    expect(row.op).toBe("contains");
  });

  it("accepts a base filter row with optional value2", () => {
    const row: FilterRow<BaseFilterField> = {
      id: "f2",
      field: "date",
      op: "between",
      value: "2026-01-01",
      value2: "2026-03-01",
    };
    expect(row.value2).toBe("2026-03-01");
  });

  it("supports all base filter fields", () => {
    const fields: BaseFilterField[] = ["external_id", "date", "responses", "audio_tokens"];
    expect(fields).toHaveLength(4);
  });

  it("supports all admin filter fields (base + admin-only)", () => {
    const adminFields: AdminFilterField[] = [
      "external_id",
      "date",
      "responses",
      "audio_tokens",
      "note",
      "rating",
    ];
    expect(adminFields).toHaveLength(6);
  });
});

describe("filter operations type coverage", () => {
  it("TextFilterOp covers expected operations", () => {
    const ops: TextFilterOp[] = ["", "exists", "not_exists", "equals", "not_equals", "contains", "not_contains"];
    expect(ops).toHaveLength(7);
  });

  it("DateFilterOp covers expected operations", () => {
    const ops: DateFilterOp[] = ["after", "before", "between", "last_7_days", "last_30_days", "this_week", "this_month"];
    expect(ops).toHaveLength(7);
  });

  it("ResponsesFilterOp covers expected operations", () => {
    const ops: ResponsesFilterOp[] = ["at_least", "at_most", "between", "equals"];
    expect(ops).toHaveLength(4);
  });

  it("AudioFilterOp covers expected operations", () => {
    const ops: AudioFilterOp[] = ["has", "not_has", "at_least", "at_most", "between"];
    expect(ops).toHaveLength(5);
  });
});
