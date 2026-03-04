"use client";

import * as React from "react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type {
  FilterRow,
  TextFilterOp,
  DateFilterOp,
  ResponsesFilterOp,
  AudioFilterOp,
} from "@/lib/session-filters";

const TEXT_OPS: Array<{ value: TextFilterOp; label: string }> = [
  { value: "", label: "Any" },
  { value: "exists", label: "Exists" },
  { value: "not_exists", label: "Does not exist" },
  { value: "equals", label: "Equals" },
  { value: "not_equals", label: "Does not equal" },
  { value: "contains", label: "Contains" },
  { value: "not_contains", label: "Does not contain" },
];

const DATE_OPS: Array<{ value: DateFilterOp; label: string }> = [
  { value: "after", label: "After" },
  { value: "before", label: "Before" },
  { value: "between", label: "Between" },
  { value: "last_7_days", label: "Last 7 days" },
  { value: "last_30_days", label: "Last 30 days" },
  { value: "this_week", label: "This week" },
  { value: "this_month", label: "This month" },
];

const RESPONSES_OPS: Array<{ value: ResponsesFilterOp; label: string }> = [
  { value: "at_least", label: "At least" },
  { value: "at_most", label: "At most" },
  { value: "between", label: "Between" },
  { value: "equals", label: "Equals" },
];

const AUDIO_OPS: Array<{ value: AudioFilterOp; label: string }> = [
  { value: "has", label: "Has audio" },
  { value: "not_has", label: "Does not have audio" },
  { value: "at_least", label: "At least" },
  { value: "at_most", label: "At most" },
  { value: "between", label: "Between" },
];

const KNOWN_NON_TEXT = new Set(["date", "responses", "audio_tokens", "rating"]);

interface FilterBarProps<F extends string> {
  rows: FilterRow<F>[];
  onRowsChange: React.Dispatch<React.SetStateAction<FilterRow<F>[]>>;
  fieldOptions: Array<{ value: F; label: string }>;
  defaultOperatorForField: (field: F) => string;
  ratingOperatorOptions?: Array<{ value: string; label: string }>;
  ratingValueOptions?: Array<{ value: string; label: string }>;
}

export function FilterBar<F extends string>({
  rows,
  onRowsChange,
  fieldOptions,
  defaultOperatorForField,
  ratingOperatorOptions,
  ratingValueOptions,
}: FilterBarProps<F>) {
  const usedFields = new Set(rows.map((r) => r.field));
  const canAdd = rows.length < fieldOptions.length;

  const add = () => {
    const next = fieldOptions.find((o) => !usedFields.has(o.value))?.value;
    if (!next) return;
    onRowsChange((prev) =>
      prev.concat({
        id: `filter-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        field: next,
        op: defaultOperatorForField(next),
        value: "",
      })
    );
  };

  const remove = (rowId: string) => {
    onRowsChange((prev) => prev.filter((r) => r.id !== rowId));
  };

  const update = (rowId: string, updates: Partial<FilterRow<F>>) => {
    onRowsChange((prev) =>
      prev.map((r) => (r.id === rowId ? { ...r, ...updates } : r))
    );
  };

  return (
    <div>
      <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">
        Filters
      </div>
      <div className="mt-3 grid gap-3">
        {rows.map((row) => {
          const fieldOpts = fieldOptions.filter(
            (o) => o.value === row.field || !usedFields.has(o.value)
          );
          const isText = !KNOWN_NON_TEXT.has(row.field);
          const isRating = row.field === "rating";
          const isDate = row.field === "date";
          const isResponses = row.field === "responses";
          const isAudio = row.field === "audio_tokens";
          const textDisabled = row.op === "" || row.op === "exists" || row.op === "not_exists";
          const dateOp = row.op as DateFilterOp;
          const responsesOp = row.op as ResponsesFilterOp;
          const audioOp = row.op as AudioFilterOp;
          const showDateInputs = ["after", "before", "between"].includes(dateOp);
          const showDateRange = dateOp === "between";
          const showResponsesRange = responsesOp === "between";
          const showAudioRange = audioOp === "between";
          const audioDisabled = audioOp === "has" || audioOp === "not_has";

          return (
            <div
              key={row.id}
              className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-secondary)] p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <div className="min-w-[160px] flex-1 sm:flex-none sm:w-[180px]">
                  <Select
                    value={row.field}
                    onChange={(value) => {
                      const field = value as F;
                      update(row.id, {
                        field,
                        op: defaultOperatorForField(field),
                        value: "",
                        value2: "",
                      });
                    }}
                    options={fieldOpts}
                  />
                </div>
                <div className="min-w-[180px] flex-1">
                  <Select
                    value={row.op}
                    onChange={(value) =>
                      update(row.id, { op: value as string, value: "", value2: "" })
                    }
                    options={
                      isText
                        ? TEXT_OPS
                        : isRating && ratingOperatorOptions
                        ? ratingOperatorOptions
                        : isDate
                        ? DATE_OPS
                        : isAudio
                        ? AUDIO_OPS
                        : RESPONSES_OPS
                    }
                  />
                </div>
                <div className="flex-1 min-w-[220px]">
                  {isText && (
                    <Input
                      value={row.value}
                      onChange={(e) => update(row.id, { value: e.target.value })}
                      placeholder="Value"
                      disabled={textDisabled}
                    />
                  )}

                  {isRating && ratingValueOptions && (
                    <Select
                      value={row.value}
                      onChange={(value) => update(row.id, { value })}
                      options={ratingValueOptions}
                    />
                  )}

                  {isDate && !showDateInputs && (
                    <div className="flex items-center text-xs text-[var(--text-muted)]">
                      Date range auto-set
                    </div>
                  )}

                  {isDate && showDateInputs && !showDateRange && (
                    <Input
                      type="date"
                      value={row.value}
                      onChange={(e) => update(row.id, { value: e.target.value })}
                    />
                  )}

                  {isDate && showDateRange && (
                    <div className="grid gap-2 sm:grid-cols-2">
                      <Input
                        type="date"
                        value={row.value}
                        onChange={(e) => update(row.id, { value: e.target.value })}
                        placeholder="Start date"
                      />
                      <Input
                        type="date"
                        value={row.value2 || ""}
                        onChange={(e) => update(row.id, { value2: e.target.value })}
                        placeholder="End date"
                      />
                    </div>
                  )}

                  {isResponses && !showResponsesRange && (
                    <Input
                      type="number"
                      min={0}
                      step={1}
                      inputMode="numeric"
                      value={row.value}
                      onChange={(e) => update(row.id, { value: e.target.value })}
                      placeholder="Value"
                    />
                  )}

                  {isResponses && showResponsesRange && (
                    <div className="grid gap-2 sm:grid-cols-2">
                      <Input
                        type="number"
                        min={0}
                        step={1}
                        inputMode="numeric"
                        value={row.value}
                        onChange={(e) => update(row.id, { value: e.target.value })}
                        placeholder="Min"
                      />
                      <Input
                        type="number"
                        min={0}
                        step={1}
                        inputMode="numeric"
                        value={row.value2 || ""}
                        onChange={(e) => update(row.id, { value2: e.target.value })}
                        placeholder="Max"
                      />
                    </div>
                  )}

                  {isAudio && !showAudioRange && (
                    <Input
                      type="number"
                      min={0}
                      step={1}
                      inputMode="numeric"
                      value={row.value}
                      onChange={(e) => update(row.id, { value: e.target.value })}
                      placeholder="Tokens"
                      disabled={audioDisabled}
                    />
                  )}

                  {isAudio && showAudioRange && (
                    <div className="grid gap-2 sm:grid-cols-2">
                      <Input
                        type="number"
                        min={0}
                        step={1}
                        inputMode="numeric"
                        value={row.value}
                        onChange={(e) => update(row.id, { value: e.target.value })}
                        placeholder="Min"
                      />
                      <Input
                        type="number"
                        min={0}
                        step={1}
                        inputMode="numeric"
                        value={row.value2 || ""}
                        onChange={(e) => update(row.id, { value2: e.target.value })}
                        placeholder="Max"
                      />
                    </div>
                  )}
                </div>
                <button
                  onClick={() => remove(row.id)}
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
          onClick={add}
          disabled={!canAdd}
          className="rounded-full border border-[var(--border-default)] bg-white px-3 py-1 text-xs font-semibold text-[var(--text-secondary)] shadow-[var(--shadow-sm)] disabled:opacity-50"
        >
          + Add filter
        </button>
      </div>
    </div>
  );
}
