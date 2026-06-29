// Pure, unit-tested helpers for the Excel Templates page. Kept in their own
// module so the page file only exports a component (react-refresh rule).

export type Agg = "sum" | "avg" | "min" | "max" | "last" | "delta";

export interface MappingRow {
  col_letter: string;
  source_code: string;
  label: string;
  tag_id: number | null;
  agg: Agg;
  enabled: boolean;
  source_type: "tag" | "variable";
  variable_id: number | null;
  write_mode: "series" | "reduce" | null;
  reduce_op: "sum" | "avg" | "min" | "max" | "last" | null;
  target_mode: "column" | "cell";
  target_cell: string | null;
  variable_code_snapshot: string | null;
}

export interface TemplateMeta {
  name: string;
  description: string;
  file_b64: string;
  sheet_name: string;
  header_row: number;
  date_col: string;
  data_start_row: number;
  date_mode: "write" | "match";
}

export const AGGS: Agg[] = ["sum", "avg", "min", "max", "last", "delta"];

export function applyAggChange(rows: MappingRow[], col: string, agg: Agg): MappingRow[] {
  return rows.map((r) => (r.col_letter === col ? { ...r, agg } : r));
}

export function toSavePayload(meta: TemplateMeta, rows: MappingRow[]) {
  return {
    ...meta,
    columns: rows
      .filter((r) => r.enabled && (r.tag_id != null || (r.source_type === "variable" && r.variable_id != null)))
      .map((r) => ({
        col_letter: r.col_letter,
        tag_id: r.source_type === "tag" ? r.tag_id : null,
        agg: r.agg,
        source_code: r.source_code,
        enabled: r.enabled,
        source_type: r.source_type,
        variable_id: r.source_type === "variable" ? r.variable_id : null,
        write_mode: r.write_mode ?? null,
        reduce_op: r.reduce_op ?? null,
        target_mode: r.target_mode,
        target_cell: r.target_cell ?? null,
      })),
  };
}

// Attach the JWT the way the axios client does (localStorage 'token'); a raw
// fetch would otherwise get a 401.
export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = localStorage.getItem("token");
  return token ? { ...extra, Authorization: `Bearer ${token}` } : { ...extra };
}
