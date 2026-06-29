import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { listFacilityVariables } from "../api/client";
import {
  AGGS,
  applyAggChange,
  authHeaders,
  toSavePayload,
  type Agg,
  type MappingRow,
  type TemplateMeta,
} from "./excelTemplates.helpers";

async function apiInspect(file: File): Promise<{
  sheet_name: string; header_row: number; date_col: string;
  data_start_row: number; date_mode: "write"; columns: MappingRow[];
}> {
  const fd = new FormData();
  fd.append("file", file);
  // The browser sets Content-Type (with the boundary) for FormData; don't set it manually.
  const res = await fetch("/api/excel-templates/inspect", {
    method: "POST",
    headers: authHeaders(),
    body: fd,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function apiList() {
  const res = await fetch("/api/excel-templates", { headers: authHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function apiSave(payload: ReturnType<typeof toSavePayload>) {
  const res = await fetch("/api/excel-templates", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function fileToB64(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  let bin = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

export default function ExcelTemplates() {
  const { t } = useTranslation("excelTemplates");
  const { can } = useAuth();
  const qc = useQueryClient();
  const [view, setView] = useState<"list" | "map">("list");
  const [rows, setRows] = useState<MappingRow[]>([]);
  const [meta, setMeta] = useState<TemplateMeta | null>(null);

  const templates = useQuery({ queryKey: ["excel-templates"], queryFn: apiList });

  const { data: facilityVars = [] } = useQuery({
    queryKey: ["facility-variables"],
    queryFn: () => listFacilityVariables().then((r) => r.data),
  });

  const saveMut = useMutation({
    mutationFn: () => apiSave(toSavePayload(meta!, rows)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["excel-templates"] });
      setView("list");
    },
  });

  // Generic per-row patcher — mirrors the inline setRows updaters for tag_id/agg/enabled.
  const update = (col: string, patch: Partial<MappingRow>) =>
    setRows((rs) => rs.map((r) => (r.col_letter === col ? { ...r, ...patch } : r)));

  async function onUpload(file: File) {
    const proposal = await apiInspect(file);
    const b64 = await fileToB64(file);
    setMeta({
      name: file.name.replace(/\.xlsx$/i, ""),
      description: "",
      file_b64: b64,
      sheet_name: proposal.sheet_name,
      header_row: proposal.header_row,
      date_col: proposal.date_col,
      data_start_row: proposal.data_start_row,
      date_mode: proposal.date_mode,
    });
    // Carry-forward 1: inject defaults for variable-binding fields that
    // inspect_template does not return, so the controlled selects are never
    // left with undefined values.
    setRows(
      proposal.columns.map((c) => ({
        ...c,
        source_type: c.source_type ?? "tag",
        variable_id: c.variable_id ?? null,
        write_mode: c.write_mode ?? null,
        reduce_op: c.reduce_op ?? null,
        target_mode: c.target_mode ?? "column",
        target_cell: c.target_cell ?? null,
        variable_code_snapshot: c.variable_code_snapshot ?? null,
      })),
    );
    setView("map");
  }

  async function generate(id: number) {
    const now = new Date();
    const y = now.getFullYear();
    const m = now.getMonth() + 1;
    const res = await fetch(`/api/excel-templates/${id}/generate?year=${y}&month=${m}`, {
      method: "POST",
      headers: authHeaders(),
    });
    if (res.status === 409) {
      const body = await res.json();
      alert(body.detail);
      return;
    }
    if (!res.ok) {
      alert(await res.text());
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `rapor_${y}_${String(m).padStart(2, "0")}.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (view === "map" && meta) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-semibold mb-4 text-white">{t("map_title", { name: meta.name })}</h1>
        <table className="w-full text-sm text-gray-300">
          <thead>
            <tr className="text-start border-b border-edge text-gray-400">
              <th>{t("map_col")}</th>
              <th>{t("map_label")}</th>
              <th>{t("map_sensor")}</th>
              <th>{t("map_tag_id")}</th>
              <th>{t("map_agg")}</th>
              <th>{t("map_enabled")}</th>
              <th>{t("map_source_type")}</th>
              <th>{t("map_variable")}</th>
              <th>{t("map_write_mode")}</th>
              <th>{t("map_reduce_op")}</th>
              <th>{t("map_target_cell")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.col_letter} className="border-b border-edge">
                <td>{r.col_letter}</td>
                <td>{r.label}</td>
                <td>{r.source_code || "—"}</td>
                <td>
                  <input
                    type="number"
                    className="w-20 bg-transparent border border-edge-strong rounded px-1"
                    value={r.tag_id ?? ""}
                    onChange={(e) =>
                      setRows((rs) => rs.map((x) => x.col_letter === r.col_letter
                        ? { ...x, tag_id: e.target.value ? Number(e.target.value) : null } : x))}
                  />
                </td>
                <td>
                  <select
                    className="bg-transparent border border-edge-strong rounded px-1"
                    value={r.agg}
                    onChange={(e) => setRows((rs) => applyAggChange(rs, r.col_letter, e.target.value as Agg))}
                  >
                    {AGGS.map((a) => <option key={a} value={a}>{a}</option>)}
                  </select>
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={r.enabled}
                    onChange={(e) => setRows((rs) => rs.map((x) => x.col_letter === r.col_letter
                      ? { ...x, enabled: e.target.checked } : x))}
                  />
                </td>
                <td>
                  <select
                    aria-label={t("map_source_type")}
                    className="bg-transparent border border-edge-strong rounded px-1"
                    value={r.source_type}
                    onChange={(e) => update(r.col_letter, { source_type: e.target.value as "tag" | "variable" })}
                  >
                    <option value="tag">tag</option>
                    <option value="variable">variable</option>
                  </select>
                </td>
                <td>
                  {r.source_type === "variable" ? (
                    <select
                      aria-label={t("map_variable")}
                      className="bg-transparent border border-edge-strong rounded px-1"
                      value={r.variable_id ?? 0}
                      onChange={(e) => update(r.col_letter, { variable_id: Number(e.target.value) || null })}
                    >
                      <option value={0}>—</option>
                      {facilityVars.filter((v) => v.is_active).map((v) => (
                        <option key={v.id} value={v.id}>{v.code}</option>
                      ))}
                    </select>
                  ) : <span className="text-gray-600">—</span>}
                </td>
                <td>
                  {r.source_type === "variable" ? (
                    <select
                      aria-label={t("map_write_mode")}
                      className="bg-transparent border border-edge-strong rounded px-1"
                      value={r.write_mode ?? "series"}
                      onChange={(e) => update(r.col_letter, { write_mode: e.target.value as "series" | "reduce" })}
                    >
                      <option value="series">series</option>
                      <option value="reduce">reduce</option>
                    </select>
                  ) : <span className="text-gray-600">—</span>}
                </td>
                <td>
                  {r.source_type === "variable" && r.write_mode === "reduce" ? (
                    <select
                      aria-label={t("map_reduce_op")}
                      className="bg-transparent border border-edge-strong rounded px-1"
                      value={r.reduce_op ?? "sum"}
                      onChange={(e) => update(r.col_letter, { reduce_op: e.target.value as MappingRow["reduce_op"] })}
                    >
                      {(["sum", "avg", "min", "max", "last"] as const).map((o) => (
                        <option key={o} value={o}>{o}</option>
                      ))}
                    </select>
                  ) : <span className="text-gray-600">—</span>}
                </td>
                <td>
                  {r.source_type === "variable" ? (
                    <div className="flex items-center gap-1">
                      <select
                        aria-label={t("map_target_mode")}
                        className="bg-transparent border border-edge-strong rounded px-1"
                        value={r.target_mode}
                        onChange={(e) => update(r.col_letter, { target_mode: e.target.value as "column" | "cell" })}
                      >
                        <option value="column">column</option>
                        <option value="cell">cell</option>
                      </select>
                      {r.target_mode === "cell" && (
                        <input
                          aria-label={t("map_target_cell")}
                          className="w-16 bg-transparent border border-edge-strong rounded px-1"
                          value={r.target_cell ?? ""}
                          onChange={(e) => update(r.col_letter, { target_cell: e.target.value || null })}
                        />
                      )}
                    </div>
                  ) : <span className="text-gray-600">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 flex gap-2">
          <button className="px-3 py-1 rounded bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/30" onClick={() => saveMut.mutate()}>{t("save")}</button>
          <button className="px-3 py-1 rounded border border-edge-strong text-gray-300" onClick={() => setView("list")}>{t("cancel")}</button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4 text-white">{t("title")}</h1>
      {can("report_template:create") && (
        <label className="inline-block mb-4 px-3 py-1 rounded bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/30 cursor-pointer">
          {t("upload")}
          <input
            type="file"
            accept=".xlsx"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])}
          />
        </label>
      )}
      <table className="w-full text-sm text-gray-300">
        <thead>
          <tr className="text-start border-b border-edge text-gray-400">
            <th>{t("col_name")}</th><th>{t("col_sheet")}</th><th>{t("col_mapped")}</th><th>{t("col_action")}</th>
          </tr>
        </thead>
        <tbody>
          {(templates.data ?? []).map((tpl: { id: number; name: string; sheet_name: string; columns: unknown[] }) => (
            <tr key={tpl.id} className="border-b border-edge">
              <td>{tpl.name}</td>
              <td>{tpl.sheet_name}</td>
              <td>{tpl.columns.length}</td>
              <td><button className="px-2 py-0.5 rounded bg-green-600 text-white" onClick={() => generate(tpl.id)}>{t("generate")}</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
