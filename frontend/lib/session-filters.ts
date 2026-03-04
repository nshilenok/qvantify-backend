export type BaseFilterField = "external_id" | "date" | "responses" | "audio_tokens";
export type AdminFilterField = BaseFilterField | "note" | "rating";

export type TextFilterOp = "" | "exists" | "not_exists" | "equals" | "not_equals" | "contains" | "not_contains";
export type DateFilterOp = "after" | "before" | "between" | "last_7_days" | "last_30_days" | "this_week" | "this_month";
export type ResponsesFilterOp = "at_least" | "at_most" | "between" | "equals";
export type AudioFilterOp = "has" | "not_has" | "at_least" | "at_most" | "between";

export interface FilterRow<F extends string = string> {
  id: string;
  field: F;
  op: string;
  value: string;
  value2?: string;
}
