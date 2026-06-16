import { describe, expect, it } from "vitest";
import { applyAggChange, toSavePayload, type MappingRow } from "./ExcelTemplates";

const rows: MappingRow[] = [
  { col_letter: "E", source_code: "410BF103", label: "DEBİ m3/gün", tag_id: 1, agg: "sum", enabled: true },
  { col_letter: "B", source_code: "", label: "HAVA DURUMU", tag_id: null, agg: "avg", enabled: false },
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
