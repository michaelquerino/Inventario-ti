"use client";

import { Activity, CheckCircle2, Pencil, RefreshCw, ServerCrash, Timer } from "lucide-react";
import type { FormEvent } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { listMonitoring, updateMonitoringVinculo, type MonitoringItem } from "@/lib/monitoring-api";
import { getApiBaseUrlCandidates } from "@/lib/session";
import { type ThresholdSettings, defaultUiSettings } from "@/lib/ui-config";
import { Pagination } from "@/components/ui/pagination";
import { Badge, type BadgeTone } from "@/components/ui/badge";

type HealthPayload = {
  status: string;
};

type SortField = "usuario" | "localizacao" | "numero_serie" | "status" | "pending" | "cpu" | "ram" | "storage" | "updated";

const AUTO_REFRESH_MS = 60 * 60 * 1000;
const PAGE_SIZE = 20;

function usageTone(value: number, warn: number, critical: number): BadgeTone {
  if (value >= critical) return "danger";
  if (value >= warn) return "warning";
  return "success";
}

type MonitoringPanelProps = {
  thresholds?: ThresholdSettings;
};

export function MonitoringPanel({ thresholds = defaultUiSettings.thresholds }: MonitoringPanelProps) {
  const [items, setItems] = useState<MonitoringItem[]>([]);
  const [apiStatus, setApiStatus] = useState<"loading" | "online" | "offline">("loading");
  const [lastCheck, setLastCheck] = useState<string>("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [sortField, setSortField] = useState<SortField>("updated");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [editingItem, setEditingItem] = useState<MonitoringItem | null>(null);
  const [editUsuario, setEditUsuario] = useState("");
  const [editLocalizacao, setEditLocalizacao] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [page, setPage] = useState(1);

  const refreshMonitoring = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const fetchHealth = async () => {
        let lastError: unknown;
        for (const baseUrl of getApiBaseUrlCandidates()) {
          try {
            return await fetch(`${baseUrl}/api/v1/health`, {
              headers: { "X-API-Version": "v1" },
            });
          } catch (error) {
            lastError = error;
          }
        }
        throw lastError instanceof Error ? lastError : new Error("Falha de conexão com API");
      };

      const [monitoringData, healthResponse] = await Promise.all([listMonitoring(), fetchHealth()]);

      if (!healthResponse.ok) {
        setApiStatus("offline");
      } else {
        const health = (await healthResponse.json()) as HealthPayload;
        setApiStatus(health.status === "ok" ? "online" : "offline");
      }

      setItems(monitoringData);
      setLastCheck(new Date().toLocaleString("pt-BR"));
    } catch (requestError) {
      setApiStatus("offline");
      setError("Nao foi possivel atualizar monitoramento agora. Tente novamente.");
      setLastCheck(new Date().toLocaleString("pt-BR"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshMonitoring();
  }, [refreshMonitoring]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshMonitoring();
    }, AUTO_REFRESH_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [refreshMonitoring]);

  const summary = useMemo(() => {
    const maintenance = items.filter(
      (item) => item.uso_cpu_percent >= thresholds.cpuCritical || item.uso_memoria_percent >= thresholds.ramCritical,
    ).length;
    const offline = items.filter((item) => item.online_status === "offline").length;
    const pendingQueue = items.reduce((acc, item) => acc + (item.fila_pendente_local || 0), 0);
    const avgCpu = items.length
      ? items.reduce((acc, item) => acc + item.uso_cpu_percent, 0) / items.length
      : 0;
    const avgRam = items.length
      ? items.reduce((acc, item) => acc + item.uso_memoria_percent, 0) / items.length
      : 0;
    return {
      total: items.length,
      maintenance,
      offline,
      pendingQueue,
      avgCpu,
      avgRam,
    };
  }, [items, thresholds.cpuCritical, thresholds.ramCritical]);

  const sortedItems = useMemo(() => {
    const copy = [...items];
    copy.sort((a, b) => {
      let left: number | string = "";
      let right: number | string = "";

      if (sortField === "usuario") {
        left = (a.usuario || "").toLowerCase();
        right = (b.usuario || "").toLowerCase();
      } else if (sortField === "localizacao") {
        left = (a.localizacao || "").toLowerCase();
        right = (b.localizacao || "").toLowerCase();
      } else if (sortField === "numero_serie") {
        left = (a.numero_serie || "").toLowerCase();
        right = (b.numero_serie || "").toLowerCase();
      } else if (sortField === "status") {
        left = a.online_status || "offline";
        right = b.online_status || "offline";
      } else if (sortField === "pending") {
        left = a.fila_pendente_local || 0;
        right = b.fila_pendente_local || 0;
      } else if (sortField === "cpu") {
        left = a.uso_cpu_percent;
        right = b.uso_cpu_percent;
      } else if (sortField === "ram") {
        left = a.uso_memoria_percent;
        right = b.uso_memoria_percent;
      } else if (sortField === "storage") {
        left = a.uso_disco_percent;
        right = b.uso_disco_percent;
      } else {
        left = a.ultima_atualizacao || "";
        right = b.ultima_atualizacao || "";
      }

      if (left < right) return sortDirection === "asc" ? -1 : 1;
      if (left > right) return sortDirection === "asc" ? 1 : -1;
      return 0;
    });
    return copy;
  }, [items, sortDirection, sortField]);

  const pagedItems = useMemo(
    () => sortedItems.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [sortedItems, page],
  );

  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(sortedItems.length / PAGE_SIZE));
    if (page > totalPages) setPage(totalPages);
  }, [sortedItems.length, page]);

  function toggleSort(field: SortField) {
    setPage(1);
    if (sortField === field) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortField(field);
    setSortDirection("desc");
  }

  function sortIndicator(field: SortField): string {
    if (sortField !== field) return "";
    return sortDirection === "asc" ? " ↑" : " ↓";
  }

  function openEditModal(item: MonitoringItem) {
    setEditingItem(item);
    setEditUsuario(item.usuario || "");
    setEditLocalizacao(item.localizacao || "");
    setSaveError("");
  }

  function closeEditModal() {
    setEditingItem(null);
    setSaveError("");
  }

  async function handleSaveVinculo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingItem) return;

    const trimmedUsuario = editUsuario.trim();
    const trimmedLocalizacao = editLocalizacao.trim();
    const payload: { usuario?: string; localizacao?: string } = {};
    if (trimmedUsuario !== (editingItem.usuario || "")) {
      payload.usuario = trimmedUsuario;
    }
    if (trimmedLocalizacao !== (editingItem.localizacao || "")) {
      payload.localizacao = trimmedLocalizacao;
    }
    if (Object.keys(payload).length === 0) {
      setEditingItem(null);
      return;
    }

    setSaving(true);
    setSaveError("");
    try {
      await updateMonitoringVinculo(editingItem.numero_serie, payload);
      setEditingItem(null);
      await refreshMonitoring();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-brand-600">Monitoramento</p>
          <h3 className="text-2xl font-semibold text-slate-900">Status operacional</h3>
          <p className="text-sm text-slate-500">Acompanhamento em tempo real do backend e dos ativos.</p>
        </div>
        <button
          onClick={() => void refreshMonitoring()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-60"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Atualizar
        </button>
      </div>

      {error ? <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}

      <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article className="rounded-2xl border border-slate-200 p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-500">API</p>
            {apiStatus === "online" ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            ) : apiStatus === "offline" ? (
              <ServerCrash className="h-5 w-5 text-red-600" />
            ) : (
              <Activity className="h-5 w-5 text-slate-400" />
            )}
          </div>
          <p className="mt-3 text-2xl font-semibold text-slate-900">
            {apiStatus === "online" ? "Online" : apiStatus === "offline" ? "Offline" : "Verificando..."}
          </p>
        </article>

        <article className="rounded-2xl border border-slate-200 p-4">
          <p className="text-sm text-slate-500">Notebooks monitorados</p>
          <p className="mt-3 text-2xl font-semibold text-slate-900">{summary.total}</p>
        </article>

        <article className="rounded-2xl border border-slate-200 p-4">
          <p className="text-sm text-slate-500">Offline sem heartbeat</p>
          <p className="mt-3 text-2xl font-semibold text-red-700">{summary.offline}</p>
        </article>

        <article className="rounded-2xl border border-slate-200 p-4">
          <p className="text-sm text-slate-500">Fila pendente total</p>
          <p className="mt-3 text-2xl font-semibold text-amber-700">{summary.pendingQueue}</p>
        </article>

        <article className="rounded-2xl border border-slate-200 p-4">
          <p className="text-sm text-slate-500">Alertas (CPU/RAM)</p>
          <p className="mt-3 text-2xl font-semibold text-amber-600">{summary.maintenance}</p>
        </article>

        <article className="rounded-2xl border border-slate-200 p-4 md:col-span-2 xl:col-span-1">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-500">Última checagem</p>
            <Timer className="h-4 w-4 text-slate-400" />
          </div>
          <p className="mt-3 text-sm font-medium text-slate-900">{lastCheck || "—"}</p>
        </article>
      </div>

      <div className="mt-5 rounded-2xl border border-slate-200">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">
                <button onClick={() => toggleSort("usuario")} className="text-left">
                  Usuário{sortIndicator("usuario")}
                </button>
              </th>
              <th className="px-4 py-3 font-medium">
                <button onClick={() => toggleSort("localizacao")} className="text-left">
                  Localização{sortIndicator("localizacao")}
                </button>
              </th>
              <th className="px-4 py-3 font-medium">
                <button onClick={() => toggleSort("numero_serie")} className="text-left">
                  Nº Série{sortIndicator("numero_serie")}
                </button>
              </th>
              <th className="px-4 py-3 font-medium">
                <button onClick={() => toggleSort("status")} className="text-left">
                  Status{sortIndicator("status")}
                </button>
              </th>
              <th className="px-4 py-3 font-medium">
                <button onClick={() => toggleSort("pending")} className="text-left">
                  Pendências envio{sortIndicator("pending")}
                </button>
              </th>
              <th className="px-4 py-3 font-medium">
                <button onClick={() => toggleSort("cpu")} className="text-left">
                  CPU{sortIndicator("cpu")}
                </button>
              </th>
              <th className="px-4 py-3 font-medium">
                <button onClick={() => toggleSort("ram")} className="text-left">
                  RAM{sortIndicator("ram")}
                </button>
              </th>
              <th className="px-4 py-3 font-medium">
                <button onClick={() => toggleSort("storage")} className="text-left">
                  Armazenamento{sortIndicator("storage")}
                </button>
              </th>
              <th className="px-4 py-3 font-medium">
                <button onClick={() => toggleSort("updated")} className="text-left">
                  Atualização{sortIndicator("updated")}
                </button>
              </th>
              <th className="px-4 py-3 font-medium">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr>
                <td className="px-4 py-6 text-slate-500" colSpan={10}>
                  Carregando monitoramento...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-slate-500" colSpan={10}>
                  Nenhum item de monitoramento encontrado.
                </td>
              </tr>
            ) : (
              pagedItems.map((item) => (
                <tr key={item.numero_serie} className="hover:bg-slate-50">
                  <td className="px-4 py-3">{item.usuario || "—"}</td>
                  <td className="px-4 py-3">{item.localizacao || "—"}</td>
                  <td className="px-4 py-3">{item.numero_serie || "—"}</td>
                  <td className="px-4 py-3">
                    <Badge tone={item.online_status === "online" ? "success" : "danger"}>
                      {item.online_status === "online" ? "Online" : "Offline"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">{item.fila_pendente_local || 0}</td>
                  <td className="px-4 py-3">
                    <Badge tone={usageTone(item.uso_cpu_percent, thresholds.cpuWarn, thresholds.cpuCritical)}>
                      {item.uso_cpu_percent.toFixed(0)}%
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span>
                        {item.memoria_usada_gb.toFixed(1)} / {item.memoria_total_gb.toFixed(1)} GB
                      </span>
                      <Badge tone={usageTone(item.uso_memoria_percent, thresholds.ramWarn, thresholds.ramCritical)}>
                        {item.uso_memoria_percent.toFixed(0)}%
                      </Badge>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span>
                        {item.armazenamento_usado_gb.toFixed(1)} / {item.armazenamento_total_gb.toFixed(1)} GB
                      </span>
                      <Badge tone={usageTone(item.uso_disco_percent, thresholds.diskWarn, thresholds.diskCritical)}>
                        {item.uso_disco_percent.toFixed(0)}%
                      </Badge>
                    </div>
                  </td>
                  <td className="px-4 py-3">{item.ultima_atualizacao || "—"}</td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => openEditModal(item)}
                      className="inline-flex items-center gap-1 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      Editar
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Pagination page={page} totalItems={sortedItems.length} pageSize={PAGE_SIZE} onPageChange={setPage} />
      </div>

      {editingItem ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 px-4">
          <div className="w-full max-w-md rounded-[28px] bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-brand-600">Vínculo</p>
                <h3 className="text-xl font-semibold text-slate-900">Editar monitoramento</h3>
                <p className="text-sm text-slate-500">Nº Série: {editingItem.numero_serie}</p>
              </div>
              <button
                type="button"
                onClick={closeEditModal}
                className="rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700"
              >
                Fechar
              </button>
            </div>

            {saveError ? (
              <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{saveError}</p>
            ) : null}

            <form className="mt-6 grid gap-4" onSubmit={handleSaveVinculo}>
              <label className="space-y-1 text-sm text-slate-700">
                <span>Usuário</span>
                <input
                  value={editUsuario}
                  onChange={(event) => setEditUsuario(event.target.value)}
                  className="h-11 w-full rounded-2xl border border-slate-200 px-4 outline-none focus:border-brand-500"
                />
                <span className="block text-xs text-slate-400">
                  Exibido só neste navegador. O agente reenvia o nome dele a cada relatório, então não altera o banco.
                </span>
              </label>
              <label className="space-y-1 text-sm text-slate-700">
                <span>Localização</span>
                <input
                  value={editLocalizacao}
                  onChange={(event) => setEditLocalizacao(event.target.value)}
                  className="h-11 w-full rounded-2xl border border-slate-200 px-4 outline-none focus:border-brand-500"
                />
              </label>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={closeEditModal}
                  className="rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700"
                >
                  Cancelar
                </button>
                <button
                  disabled={saving}
                  className="rounded-2xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
                >
                  {saving ? "Salvando..." : "Salvar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </section>
  );
}
