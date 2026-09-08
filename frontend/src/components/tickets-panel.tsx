"use client";

import { Download, FileText } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { listTickets, updateTicket, type Ticket } from "@/lib/tickets-api";
import { Pagination } from "@/components/ui/pagination";

const statusLabel: Record<Ticket["status"], string> = {
  aberto: "Aberto",
  em_andamento: "Em andamento",
  concluido: "Concluído",
};

const statusClass: Record<Ticket["status"], string> = {
  aberto: "bg-amber-100 text-amber-700",
  em_andamento: "bg-blue-100 text-blue-700",
  concluido: "bg-emerald-100 text-emerald-700",
};

const AUTO_REFRESH_MS = 60 * 1000;
const PAGE_SIZE = 10;

export function TicketsPanel() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");
  const [filtroStatus, setFiltroStatus] = useState<"todos" | Ticket["status"]>("todos");
  const [filtroCategoria, setFiltroCategoria] = useState("todas");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [respostas, setRespostas] = useState<Record<number, string>>({});
  const [salvandoId, setSalvandoId] = useState<number | null>(null);
  const [page, setPage] = useState(1);

  async function refresh() {
    try {
      const dados = await listTickets();
      setTickets(dados);
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao carregar chamados");
    } finally {
      setCarregando(false);
    }
  }

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  const categorias = useMemo(() => {
    const set = new Set<string>();
    tickets.forEach((ticket) => {
      if (ticket.categoria) set.add(ticket.categoria);
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [tickets]);

  const ticketsFiltrados = useMemo(() => {
    const inicioMs = dataInicio ? new Date(`${dataInicio}T00:00:00`).getTime() : null;
    const fimMs = dataFim ? new Date(`${dataFim}T23:59:59`).getTime() : null;

    return tickets.filter((ticket) => {
      const statusOk = filtroStatus === "todos" || ticket.status === filtroStatus;
      const categoriaOk = filtroCategoria === "todas" || ticket.categoria === filtroCategoria;
      const criadoMs = new Date(ticket.criado_em).getTime();
      const inicioOk = inicioMs === null || criadoMs >= inicioMs;
      const fimOk = fimMs === null || criadoMs <= fimMs;
      return statusOk && categoriaOk && inicioOk && fimOk;
    });
  }, [tickets, filtroStatus, filtroCategoria, dataInicio, dataFim]);

  useEffect(() => {
    setPage(1);
  }, [filtroStatus, filtroCategoria, dataInicio, dataFim]);

  const ticketsPaginados = useMemo(
    () => ticketsFiltrados.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [ticketsFiltrados, page],
  );

  function exportCsv() {
    const header = ["id", "titulo", "usuario", "patrimonio", "categoria", "status", "criado_em", "respondido_por", "resposta"];
    const linhas = ticketsFiltrados.map((ticket) =>
      [
        ticket.id,
        ticket.titulo,
        ticket.usuario || "",
        ticket.patrimonio || "",
        ticket.categoria || "",
        statusLabel[ticket.status],
        new Date(ticket.criado_em).toLocaleString("pt-BR"),
        ticket.respondido_por || "",
        ticket.resposta || "",
      ]
        .map((value) => `"${String(value).replace(/"/g, '""')}"`)
        .join(","),
    );
    const csv = [header.join(","), ...linhas].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `relatorio-chamados-${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function exportPdf() {
    const esc = (value: string) =>
      value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const html = `
      <html><head><title>Relatorio de Chamados</title></head><body>
      <h2>Relatorio de Chamados</h2>
      <p>Total filtrado: ${ticketsFiltrados.length}</p>
      <table border="1" cellspacing="0" cellpadding="6">
      <tr><th>Titulo</th><th>Usuario</th><th>Categoria</th><th>Status</th><th>Criado em</th><th>Respondido por</th></tr>
      ${ticketsFiltrados
        .map(
          (ticket) =>
            `<tr><td>${esc(ticket.titulo)}</td><td>${esc(ticket.usuario || "")}</td><td>${esc(ticket.categoria || "")}</td><td>${esc(statusLabel[ticket.status])}</td><td>${esc(new Date(ticket.criado_em).toLocaleString("pt-BR"))}</td><td>${esc(ticket.respondido_por || "")}</td></tr>`,
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

  async function handleAtualizarStatus(ticket: Ticket, status: Ticket["status"]) {
    setSalvandoId(ticket.id);
    setErro("");
    try {
      await updateTicket(ticket.id, { status });
      await refresh();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao atualizar chamado");
    } finally {
      setSalvandoId(null);
    }
  }

  async function handleResponder(ticket: Ticket) {
    const resposta = (respostas[ticket.id] || "").trim();
    if (!resposta) return;
    setSalvandoId(ticket.id);
    setErro("");
    try {
      await updateTicket(ticket.id, { resposta, status: ticket.status === "aberto" ? "em_andamento" : ticket.status });
      setRespostas((prev) => ({ ...prev, [ticket.id]: "" }));
      await refresh();
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao responder chamado");
    } finally {
      setSalvandoId(null);
    }
  }

  const contagem = useMemo(() => {
    return {
      aberto: tickets.filter((t) => t.status === "aberto").length,
      em_andamento: tickets.filter((t) => t.status === "em_andamento").length,
      concluido: tickets.filter((t) => t.status === "concluido").length,
    };
  }, [tickets]);

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-semibold text-amber-700">Abertos</p>
          <p className="mt-2 text-2xl font-semibold text-amber-700">{contagem.aberto}</p>
        </article>
        <article className="rounded-2xl border border-blue-200 bg-blue-50 p-4">
          <p className="text-sm font-semibold text-blue-700">Em andamento</p>
          <p className="mt-2 text-2xl font-semibold text-blue-700">{contagem.em_andamento}</p>
        </article>
        <article className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
          <p className="text-sm font-semibold text-emerald-700">Concluídos</p>
          <p className="mt-2 text-2xl font-semibold text-emerald-700">{contagem.concluido}</p>
        </article>
      </div>

      <div className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-semibold text-slate-900">Chamados</h3>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex gap-1.5 rounded-xl bg-slate-100 p-1">
              {(["todos", "aberto", "em_andamento", "concluido"] as const).map((opcao) => (
                <button
                  key={opcao}
                  onClick={() => setFiltroStatus(opcao)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                    filtroStatus === opcao ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"
                  }`}
                >
                  {opcao === "todos" ? "Todos" : statusLabel[opcao]}
                </button>
              ))}
            </div>
            <button
              onClick={exportCsv}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700"
            >
              <Download className="h-3.5 w-3.5" />
              CSV
            </button>
            <button
              onClick={exportPdf}
              className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-3 py-2 text-xs font-semibold text-white"
            >
              <FileText className="h-3.5 w-3.5" />
              PDF
            </button>
          </div>
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <label className="space-y-1 text-sm text-slate-700">
            <span>Categoria</span>
            <select
              value={filtroCategoria}
              onChange={(event) => setFiltroCategoria(event.target.value)}
              className="h-10 w-full rounded-xl border border-slate-200 px-3"
            >
              <option value="todas">Todas</option>
              {categorias.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm text-slate-700">
            <span>De</span>
            <input
              type="date"
              value={dataInicio}
              onChange={(event) => setDataInicio(event.target.value)}
              className="h-10 w-full rounded-xl border border-slate-200 px-3"
            />
          </label>
          <label className="space-y-1 text-sm text-slate-700">
            <span>Até</span>
            <input
              type="date"
              value={dataFim}
              onChange={(event) => setDataFim(event.target.value)}
              className="h-10 w-full rounded-xl border border-slate-200 px-3"
            />
          </label>
        </div>

        {erro ? <p className="mt-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{erro}</p> : null}

        {carregando ? (
          <p className="mt-3 text-sm text-slate-500">Carregando...</p>
        ) : ticketsFiltrados.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500">Nenhum chamado para esse filtro.</p>
        ) : (
          <div className="mt-3 space-y-3">
            {ticketsPaginados.map((ticket) => (
              <div key={ticket.id} className="rounded-2xl border border-slate-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">{ticket.titulo}</p>
                    <p className="text-xs text-slate-500">
                      {ticket.usuario || "Usuário não identificado"}
                      {ticket.patrimonio ? ` · patrimônio ${ticket.patrimonio}` : ""}
                      {ticket.categoria ? ` · ${ticket.categoria}` : ""}
                      {" · "}
                      {new Date(ticket.criado_em).toLocaleString("pt-BR")}
                    </p>
                  </div>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusClass[ticket.status]}`}>
                    {statusLabel[ticket.status]}
                  </span>
                </div>

                <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{ticket.descricao}</p>

                {ticket.resposta ? (
                  <div className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-600">
                    <p className="text-xs font-semibold uppercase text-slate-400">
                      Resposta{ticket.respondido_por ? ` de ${ticket.respondido_por}` : ""}
                    </p>
                    <p className="mt-1 whitespace-pre-wrap">{ticket.resposta}</p>
                  </div>
                ) : null}

                {ticket.status !== "concluido" ? (
                  <div className="mt-3 space-y-2">
                    <textarea
                      value={respostas[ticket.id] || ""}
                      onChange={(event) => setRespostas((prev) => ({ ...prev, [ticket.id]: event.target.value }))}
                      rows={2}
                      placeholder="Responder ao chamado..."
                      className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500"
                    />
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => void handleResponder(ticket)}
                        disabled={salvandoId === ticket.id || !(respostas[ticket.id] || "").trim()}
                        className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                      >
                        Responder
                      </button>
                      {ticket.status === "aberto" ? (
                        <button
                          onClick={() => void handleAtualizarStatus(ticket, "em_andamento")}
                          disabled={salvandoId === ticket.id}
                          className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 disabled:opacity-40"
                        >
                          Marcar em andamento
                        </button>
                      ) : null}
                      <button
                        onClick={() => void handleAtualizarStatus(ticket, "concluido")}
                        disabled={salvandoId === ticket.id}
                        className="rounded-lg border border-emerald-200 px-3 py-1.5 text-xs font-semibold text-emerald-700 disabled:opacity-40"
                      >
                        Marcar concluído
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}

        <Pagination page={page} totalItems={ticketsFiltrados.length} pageSize={PAGE_SIZE} onPageChange={setPage} bare />
      </div>
    </section>
  );
}
