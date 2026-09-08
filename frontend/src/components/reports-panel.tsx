"use client";

import { Download, FileText, Filter } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { type Asset } from "@/lib/assets-api";
import { Pagination } from "@/components/ui/pagination";

const PAGE_SIZE = 20;

type ReportsPanelProps = {
  assets: Asset[];
};

function assetsToCsv(rows: Asset[]): string {
  const header = [
    "asset_tag",
    "name",
    "status",
    "category",
    "owner",
    "location",
    "serial_number",
    "department",
    "notes",
  ];
  const body = rows.map((item) =>
    [
      item.asset_tag,
      item.name,
      item.status,
      item.category || "",
      item.owner || "",
      item.location || "",
      item.serial_number || "",
      item.department || "",
      item.notes || "",
    ]
      .map((value) => `"${String(value).replace(/"/g, '""')}"`)
      .join(","),
  );
  return [header.join(","), ...body].join("\n");
}

export function ReportsPanel({ assets }: ReportsPanelProps) {
  const [status, setStatus] = useState("all");
  const [category, setCategory] = useState("all");
  const [locationQuery, setLocationQuery] = useState("");
  const [notesQuery, setNotesQuery] = useState("");
  const [notesFilter, setNotesFilter] = useState("all");
  const [page, setPage] = useState(1);

  const categories = useMemo(() => {
    const set = new Set<string>();
    assets.forEach((item) => {
      if (item.category) set.add(item.category);
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [assets]);

  const filtered = useMemo(() => {
    return assets.filter((item) => {
      const statusOk = status === "all" || item.status === status;
      const categoryOk = category === "all" || item.category === category;
      const locationOk =
        locationQuery.trim().length === 0 ||
        (item.location || "").toLowerCase().includes(locationQuery.trim().toLowerCase());
      const temObservacao = Boolean(item.notes && item.notes.trim());
      const notesPresenceOk =
        notesFilter === "all" || (notesFilter === "with" ? temObservacao : !temObservacao);
      const notesQueryOk =
        notesQuery.trim().length === 0 ||
        (item.notes || "").toLowerCase().includes(notesQuery.trim().toLowerCase());
      return statusOk && categoryOk && locationOk && notesPresenceOk && notesQueryOk;
    });
  }, [assets, status, category, locationQuery, notesFilter, notesQuery]);

  useEffect(() => {
    setPage(1);
  }, [status, category, locationQuery, notesFilter, notesQuery]);

  const paginated = useMemo(() => filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE), [filtered, page]);

  const compliance = useMemo(() => {
    const missingOwner = filtered.filter((item) => !item.owner || !item.owner.trim()).length;
    const missingLocation = filtered.filter((item) => !item.location || !item.location.trim()).length;
    const missingSerial = filtered.filter((item) => !item.serial_number || !item.serial_number.trim()).length;
    const missingNotes = filtered.filter((item) => !item.notes || !item.notes.trim()).length;
    return { missingOwner, missingLocation, missingSerial, missingNotes };
  }, [filtered]);

  function exportCsv() {
    const csv = assetsToCsv(filtered);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `relatorio-ativos-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function exportPdf() {
    const esc = (value: string) =>
      value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const html = `
      <html><head><title>Relatorio de Ativos</title></head><body>
      <h2>Relatorio de Ativos</h2>
      <p>Total filtrado: ${filtered.length}</p>
      <table border="1" cellspacing="0" cellpadding="6">
      <tr><th>Tag</th><th>Nome</th><th>Status</th><th>Categoria</th><th>Responsavel</th><th>Localizacao</th><th>Observacoes</th></tr>
      ${filtered
        .map(
          (item) =>
            `<tr><td>${esc(item.asset_tag)}</td><td>${esc(item.name)}</td><td>${esc(item.status)}</td><td>${esc(item.category || "")}</td><td>${esc(item.owner || "")}</td><td>${esc(item.location || "")}</td><td>${esc(item.notes || "")}</td></tr>`,
        )
        .join("")}
      </table></body></html>
    `;

    const printWindow = window.open("", "_blank", "width=1000,height=700");
    if (!printWindow) return;
    printWindow.document.write(html);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  }

  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-2xl font-semibold text-slate-900">Relatórios</h3>
          <p className="mt-1 text-sm text-slate-500">Filtros operacionais e exportação CSV/PDF.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={exportCsv}
            className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700"
          >
            <Download className="h-4 w-4" />
            Exportar CSV
          </button>
          <button
            onClick={exportPdf}
            className="inline-flex items-center gap-2 rounded-2xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white"
          >
            <FileText className="h-4 w-4" />
            Exportar PDF
          </button>
        </div>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <label className="space-y-1 text-sm text-slate-700">
          <span>Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="h-10 w-full rounded-xl border border-slate-200 px-3">
            <option value="all">Todos</option>
            <option value="active">Ativo</option>
            <option value="maintenance">Manutenção</option>
            <option value="retired">Baixado</option>
          </select>
        </label>
        <label className="space-y-1 text-sm text-slate-700">
          <span>Categoria</span>
          <select value={category} onChange={(e) => setCategory(e.target.value)} className="h-10 w-full rounded-xl border border-slate-200 px-3">
            <option value="all">Todas</option>
            {categories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm text-slate-700">
          <span>Localização</span>
          <input
            value={locationQuery}
            onChange={(e) => setLocationQuery(e.target.value)}
            className="h-10 w-full rounded-xl border border-slate-200 px-3"
            placeholder="Filtrar por local"
          />
        </label>
        <label className="space-y-1 text-sm text-slate-700">
          <span>Observações</span>
          <select
            value={notesFilter}
            onChange={(e) => setNotesFilter(e.target.value)}
            className="h-10 w-full rounded-xl border border-slate-200 px-3"
          >
            <option value="all">Todos</option>
            <option value="with">Com observação</option>
            <option value="without">Sem observação</option>
          </select>
        </label>
        <label className="space-y-1 text-sm text-slate-700">
          <span>Buscar na observação</span>
          <input
            value={notesQuery}
            onChange={(e) => setNotesQuery(e.target.value)}
            className="h-10 w-full rounded-xl border border-slate-200 px-3"
            placeholder="Filtrar por texto na observação"
          />
        </label>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <article className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm text-slate-500">Sem responsável</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900">{compliance.missingOwner}</p>
        </article>
        <article className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm text-slate-500">Sem localização</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900">{compliance.missingLocation}</p>
        </article>
        <article className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm text-slate-500">Sem nº de série</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900">{compliance.missingSerial}</p>
        </article>
        <article className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-sm text-slate-500">Sem observação</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900">{compliance.missingNotes}</p>
        </article>
      </div>

      <div className="mt-5 rounded-2xl border border-slate-200">
      <div className="overflow-x-auto">
        <table className="min-w-full table-fixed divide-y divide-slate-200 text-left text-sm">
          <colgroup>
            <col className="w-28" />
            <col className="w-40" />
            <col className="w-24" />
            <col className="w-32" />
            <col className="w-28" />
            <col className="w-28" />
            <col className="w-56" />
          </colgroup>
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Tag</th>
              <th className="px-4 py-3 font-medium">Nome</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Categoria</th>
              <th className="px-4 py-3 font-medium">Responsável</th>
              <th className="px-4 py-3 font-medium">Localização</th>
              <th className="px-4 py-3 font-medium">Observações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-slate-500">
                  Nenhum ativo para os filtros selecionados.
                </td>
              </tr>
            ) : (
              paginated.map((item) => (
                <tr key={item.id}>
                  <td className="truncate px-4 py-3 font-semibold text-brand-700">{item.asset_tag}</td>
                  <td className="truncate px-4 py-3">{item.name}</td>
                  <td className="truncate px-4 py-3">{item.status}</td>
                  <td className="truncate px-4 py-3">{item.category || "—"}</td>
                  <td className="truncate px-4 py-3">{item.owner || "—"}</td>
                  <td className="truncate px-4 py-3">{item.location || "—"}</td>
                  <td className="truncate px-4 py-3" title={item.notes || ""}>
                    {item.notes || "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Pagination page={page} totalItems={filtered.length} pageSize={PAGE_SIZE} onPageChange={setPage} />
      </div>

      <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
        <Filter className="h-3.5 w-3.5" />
        {filtered.length} itens no relatório filtrado.
      </div>
    </section>
  );
}
