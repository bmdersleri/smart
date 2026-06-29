import { afterEach, describe, expect, it, vi } from "vitest";
import { applyAggChange, authHeaders, toSavePayload, type MappingRow } from "./excelTemplates.helpers";

// Defaults for the variable-binding fields added in Task 8 (not set by legacy rows).
const rowDefaults = {
  source_type: "tag" as const,
  variable_id: null,
  write_mode: null,
  reduce_op: null,
  target_mode: "column" as const,
  target_cell: null,
  variable_code_snapshot: null,
};

const rows: MappingRow[] = [
  { ...rowDefaults, col_letter: "E", source_code: "410BF103", label: "DEBİ m3/gün", tag_id: 1, agg: "sum", enabled: true },
  { ...rowDefaults, col_letter: "B", source_code: "", label: "HAVA DURUMU", tag_id: null, agg: "avg", enabled: false },
];

describe("mapping grid state", () => {
  it("updates agg for one column only", () => {
    const next = applyAggChange(rows, "E", "delta");
    expect(next.find((r) => r.col_letter === "E")?.agg).toBe("delta");
    expect(next.find((r) => r.col_letter === "B")?.agg).toBe("avg");
  });

  it("save payload drops disabled/unmapped rows", () => {
    const payload = toSavePayload(
      { name: "T", description: "", file_b64: "AA==", sheet_name: "S", header_row: 2, date_col: "D", data_start_row: 3, date_mode: "write" },
      rows,
    );
    expect(payload.columns).toHaveLength(1);
    expect(payload.columns[0].col_letter).toBe("E");
  });
});

describe("authHeaders", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("adds Bearer token from localStorage when present", () => {
    vi.stubGlobal("localStorage", { getItem: () => "abc123" });
    expect(authHeaders()).toEqual({ Authorization: "Bearer abc123" });
    expect(authHeaders({ "Content-Type": "application/json" })).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer abc123",
    });
  });

  it("omits Authorization when no token", () => {
    vi.stubGlobal("localStorage", { getItem: () => null });
    expect(authHeaders()).toEqual({});
    expect(authHeaders({ "Content-Type": "application/json" })).toEqual({
      "Content-Type": "application/json",
    });
  });
});
