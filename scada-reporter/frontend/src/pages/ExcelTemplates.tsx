import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../context/AuthContext";

export type Agg = "sum" | "avg" | "min" | "max" | "last" | "delta";

export interface MappingRow {
  col_letter: string;
  source_code: string;
  label: string;
  tag_id: number | null;
  agg: Agg;
  enabled: boolean;
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

// --- pure helpers (unit-tested) ---
export function applyAggChange(rows: MappingRow[], col: string, agg: Agg): MappingRow[] {
  return rows.map((r) => (r.col_letter === col ? { ...r, agg } : r));
}

export function toSavePayload(meta: TemplateMeta, rows: MappingRow[]) {
  return {
    ...meta,
    columns: rows
      .filter((r) => r.enabled && r.tag_id != null)
      .map((r) => ({
        col_letter: r.col_letter,
        tag_id: r.tag_id,
        agg: r.agg,
        source_code: r.source_code,
        enabled: r.enabled,
      })),
  };
}

const AGGS: Agg[] = ["sum", "avg", "min", "max", "last", "delta"];

// JWT'yi axios client'ı gibi ekle (localStorage 'token'); raw fetch yoksa 401 olur.
export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = localStorage.getItem("token");
  return token ? { ...extra, Authorization: `Bearer ${token}` } : { ...extra };
}

async function apiInspect(file: File): Promise<{
  sheet_name: string; header_row: number; date_col: string;
  data_start_row: number; date_mode: "write"; columns: MappingRow[];
}> {
  const fd = new FormData();
  fd.append("file", file);
  // FormData'da Content-Type'ı tarayıcı (boundary ile) koyar; elle koyma.
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
  const { can } = useAuth();
  const qc = useQueryClient();
  const [view, setView] = useState<"list" | "map">("list");
  const [rows, setRows] = useState<MappingRow[]>([]);
  const [meta, setMeta] = useState<TemplateMeta | null>(null);

  const templates = useQuery({ queryKey: ["excel-templates"], queryFn: apiList });

  const saveMut = useMutation({
    mutationFn: () => apiSave(toSavePayload(meta!, rows)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["excel-templates"] });
      setView("list");
    },
  });

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
    setRows(proposal.columns);
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
      <div className="p-6 text-gray-900 dark:text-gray-100">
        <h1 className="text-xl font-semibold mb-4">Şablon Eşleme — {meta.name}</h1>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b dark:border-gray-700">
              <th>Sütun</th><th>Etiket</th><th>Sensör Kodu</th><th>Tag ID</th><th>Toplama</th><th>Aktif</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.col_letter} className="border-b dark:border-gray-800">
                <td>{r.col_letter}</td>
                <td>{r.label}</td>
                <td>{r.source_code || "—"}</td>
                <td>
                  <input
                    type="number"
                    className="w-20 bg-transparent border rounded px-1"
                    value={r.tag_id ?? ""}
                    onChange={(e) =>
                      setRows((rs) => rs.map((x) => x.col_letter === r.col_letter
                        ? { ...x, tag_id: e.target.value ? Number(e.target.value) : null } : x))}
                  />
                </td>
                <td>
                  <select
                    className="bg-transparent border rounded px-1"
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
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 flex gap-2">
          <button className="px-3 py-1 rounded bg-blue-600 text-white" onClick={() => saveMut.mutate()}>Kaydet</button>
          <button className="px-3 py-1 rounded border" onClick={() => setView("list")}>İptal</button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 text-gray-900 dark:text-gray-100">
      <h1 className="text-xl font-semibold mb-4">Excel Şablonları</h1>
      {can('report_template:create') && (
        <label className="inline-block mb-4 px-3 py-1 rounded bg-blue-600 text-white cursor-pointer">
          + Şablon Yükle
          <input
            type="file"
            accept=".xlsx"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])}
          />
        </label>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left border-b dark:border-gray-700">
            <th>Ad</th><th>Sayfa</th><th>Eşlenen Sütun</th><th>İşlem</th>
          </tr>
        </thead>
        <tbody>
          {(templates.data ?? []).map((t: { id: number; name: string; sheet_name: string; columns: unknown[] }) => (
            <tr key={t.id} className="border-b dark:border-gray-800">
              <td>{t.name}</td>
              <td>{t.sheet_name}</td>
              <td>{t.columns.length}</td>
              <td><button className="px-2 py-0.5 rounded bg-green-600 text-white" onClick={() => generate(t.id)}>Oluştur</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
