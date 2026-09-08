"use client";

import {
  BarChart3,
  Bell,
  Cloud,
  Download,
  Grid2X2,
  HardDrive,
  LifeBuoy,
  MonitorSmartphone,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  RefreshCw,
  Terminal,
  TriangleAlert,
  Tags,
  UserCircle2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AssetsManager } from "@/components/assets-manager";
import { CommandsPanel } from "@/components/commands-panel";
import { MonitoringPanel } from "@/components/monitoring-panel";
import { ReportsPanel } from "@/components/reports-panel";
import { SettingsPanel } from "@/components/settings-panel";
import { TicketsPanel } from "@/components/tickets-panel";
import { listPendingAudits, resolveAllPendingAudits, resolvePendingAudit, type AuditEvent } from "@/lib/audit-api";
import { listAssets, type Asset } from "@/lib/assets-api";
import { listMonitoring, type MonitoringItem } from "@/lib/monitoring-api";
import { clearToken, getApiBaseUrlCandidates, getToken } from "@/lib/session";
import { defaultUiSettings, loadUiSettings, saveUiSettings, type UiSettings } from "@/lib/ui-config";

type SidebarSection = "dashboard" | "assets" | "monitoring" | "reports" | "tickets" | "commands" | "settings";
type TopTab = "assets" | "cloud" | "discovery" | "monitoring";

type DashboardSummary = {
  total_assets: number;
  cloud_assets: number;
  maintenance_assets: number;
  pending_audit: number;
};

type CurrentUser = {
  role: "admin" | "manager" | "viewer";
};

const sidebarItems: Array<{ id: SidebarSection; label: string; icon: typeof Grid2X2 }> = [
  { id: "dashboard", label: "Dashboard", icon: Grid2X2 },
  { id: "assets", label: "Ativos", icon: MonitorSmartphone },
  { id: "monitoring", label: "Monitoramento", icon: BarChart3 },
  { id: "reports", label: "Relatórios", icon: Tags },
  { id: "tickets", label: "Chamados", icon: LifeBuoy },
  { id: "commands", label: "Comandos", icon: Terminal },
  { id: "settings", label: "Configurações", icon: Settings },
];

const tabs: Array<{ id: TopTab; label: string }> = [
  { id: "assets", label: "Assets" },
  { id: "cloud", label: "Cloud Assets" },
  { id: "discovery", label: "Discovery" },
  { id: "monitoring", label: "Monitoramento" },
];

// "commands" não entra aqui de propósito: é restrito a admin sempre,
// independente do que estiver configurado em Configurações > Permissões.
const sectionToPermission: Partial<Record<SidebarSection, keyof UiSettings["permissions"]["admin"]>> = {
  dashboard: "dashboard",
  assets: "assets",
  monitoring: "monitoring",
  reports: "reports",
  tickets: "tickets",
  settings: "settings",
};

const AUTO_REFRESH_MS = 60 * 60 * 1000;

function assetsToCsv(assets: Asset[]): string {
  const header = [
    "id",
    "asset_tag",
    "screen_asset_tag",
    "name",
    "status",
    "category",
    "serial_number",
    "brand",
    "model",
    "location",
    "owner",
    "department",
  ];
  const rows = assets.map((asset) =>
    [
      asset.id,
      asset.asset_tag,
      asset.screen_asset_tag ?? "",
      asset.name,
      asset.status,
      asset.category ?? "",
      asset.serial_number ?? "",
      asset.brand ?? "",
      asset.model ?? "",
      asset.location ?? "",
      asset.owner ?? "",
      asset.department ?? "",
    ]
      .map((value) => `"${String(value).replace(/"/g, '""')}"`)
      .join(","),
  );
  return [header.join(","), ...rows].join("\n");
}

export default function HomePage() {
  const router = useRouter();
  const [activeSection, setActiveSection] = useState<SidebarSection>("dashboard");
  const [activeTab, setActiveTab] = useState<TopTab>("assets");
  const [headerQuery, setHeaderQuery] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [allAssets, setAllAssets] = useState<Asset[]>([]);
  const [monitoringItems, setMonitoringItems] = useState<MonitoringItem[]>([]);
  const [pendingAudits, setPendingAudits] = useState<AuditEvent[]>([]);
  const [resolvingAuditId, setResolvingAuditId] = useState<number | null>(null);
  const [resolvingAllAudits, setResolvingAllAudits] = useState(false);
  const [uiSettings, setUiSettings] = useState<UiSettings>(defaultUiSettings);
  const [currentUser, setCurrentUser] = useState<CurrentUser>({ role: "viewer" });
  const [summary, setSummary] = useState<DashboardSummary>({
    total_assets: 0,
    cloud_assets: 0,
    maintenance_assets: 0,
    pending_audit: 0,
  });

  const refreshOperationalData = useCallback(async () => {
    try {
      const [assets, monitoring, pending] = await Promise.all([listAssets(), listMonitoring(), listPendingAudits(5)]);
      setAllAssets(assets);
      setMonitoringItems(monitoring);
      setPendingAudits(pending);
    } catch {
      setActionMessage("Nao foi possivel atualizar dados operacionais agora.");
    }
  }, []);

  const refreshSummary = useCallback(async () => {
    try {
      const token = getToken();
      let response: Response | null = null;
      for (const baseUrl of getApiBaseUrlCandidates()) {
        try {
          response = await fetch(`${baseUrl}/api/v1/assets/summary`, {
            headers: {
              "Content-Type": "application/json",
              "X-API-Version": "v1",
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
          });
          break;
        } catch {
          continue;
        }
      }

      if (!response || !response.ok) {
        return;
      }

      const payload = (await response.json()) as DashboardSummary;
      setSummary(payload);
    } catch {
      // Mantém o último resumo conhecido.
    }
  }, []);

  async function handleResolveAudit(eventId: number) {
    setResolvingAuditId(eventId);
    setActionMessage("");
    try {
      await resolvePendingAudit(eventId);
      await Promise.all([refreshOperationalData(), refreshSummary()]);
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "Erro ao resolver pendência de auditoria");
    } finally {
      setResolvingAuditId(null);
    }
  }

  async function handleResolveAllAudits() {
    setResolvingAllAudits(true);
    setActionMessage("");
    try {
      await resolveAllPendingAudits();
      await Promise.all([refreshOperationalData(), refreshSummary()]);
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : "Erro ao resolver pendências de auditoria");
    } finally {
      setResolvingAllAudits(false);
    }
  }

  useEffect(() => {
    setUiSettings(loadUiSettings());
  }, []);

  useEffect(() => {
    async function loadUser() {
      try {
        const token = getToken();
        if (!token) {
          router.push("/login");
          return;
        }
        let response: Response | null = null;
        for (const baseUrl of getApiBaseUrlCandidates()) {
          try {
            response = await fetch(`${baseUrl}/api/v1/auth/me`, {
              headers: {
                "Content-Type": "application/json",
                "X-API-Version": "v1",
                Authorization: `Bearer ${token}`,
              },
            });
            break;
          } catch {
            continue;
          }
        }
        if (!response || !response.ok) {
          clearToken();
          router.push("/login");
          return;
        }
        const payload = (await response.json()) as CurrentUser;
        setCurrentUser({ role: payload.role || "viewer" });
      } catch {
        clearToken();
        router.push("/login");
        setCurrentUser({ role: "viewer" });
      }
    }

    void loadUser();
  }, []);

  useEffect(() => {
    void refreshOperationalData();
    const timer = window.setInterval(() => {
      void refreshOperationalData();
    }, AUTO_REFRESH_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [refreshOperationalData]);

  useEffect(() => {
    void refreshSummary();
  }, [refreshSummary]);

  const stats = useMemo(
    () => [
      { label: "Ativos cadastrados", value: summary.total_assets.toLocaleString("pt-BR"), icon: MonitorSmartphone },
      { label: "Cloud assets", value: summary.cloud_assets.toLocaleString("pt-BR"), icon: Cloud },
      { label: "Em manutenção", value: summary.maintenance_assets.toLocaleString("pt-BR"), icon: HardDrive },
      { label: "Auditoria pendente", value: summary.pending_audit.toLocaleString("pt-BR"), icon: ShieldCheck },
    ],
    [summary],
  );

  const dashboardAlerts = useMemo(() => {
    const staleMs = uiSettings.thresholds.staleHours * 60 * 60 * 1000;
    const now = Date.now();
    let critical = 0;
    let warning = 0;
    let stale = 0;

    monitoringItems.forEach((item) => {
      const isCritical =
        item.uso_cpu_percent >= uiSettings.thresholds.cpuCritical ||
        item.uso_memoria_percent >= uiSettings.thresholds.ramCritical ||
        item.uso_disco_percent >= uiSettings.thresholds.diskCritical;

      const isWarning =
        item.uso_cpu_percent >= uiSettings.thresholds.cpuWarn ||
        item.uso_memoria_percent >= uiSettings.thresholds.ramWarn ||
        item.uso_disco_percent >= uiSettings.thresholds.diskWarn;

      if (isCritical) {
        critical += 1;
      } else if (isWarning) {
        warning += 1;
      }

      const timestamp = item.ultima_atualizacao ? Date.parse(item.ultima_atualizacao) : NaN;
      if (!Number.isNaN(timestamp) && now - timestamp > staleMs) {
        stale += 1;
      }
    });

    return { critical, warning, stale };
  }, [monitoringItems, uiSettings.thresholds]);

  const operationalStats = useMemo(() => {
    const offline = monitoringItems.filter((item) => item.online_status === "offline").length;
    const pendingQueue = monitoringItems.reduce((acc, item) => acc + (item.fila_pendente_local || 0), 0);
    return {
      alerts: dashboardAlerts.critical + dashboardAlerts.warning,
      offline,
      pendingQueue,
    };
  }, [dashboardAlerts.critical, dashboardAlerts.warning, monitoringItems]);

  const pageTitle = useMemo(() => {
    if (activeSection === "monitoring") return "Monitoramento";
    if (activeSection === "settings") return "Configurações";
    if (activeSection === "reports") return "Relatórios";
    if (activeSection === "tickets") return "Chamados";
    if (activeSection === "commands") return "Comandos";
    return "Painel corporativo";
  }, [activeSection]);

  const isDashboard = activeSection === "dashboard";

  function showMessage(message: string) {
    setActionMessage(message);
  }

  function handleSidebarClick(section: SidebarSection) {
    if (section === "commands") {
      if (currentUser.role !== "admin") {
        showMessage("Apenas o administrador tem acesso a Comandos.");
        return;
      }
    } else {
      const rolePermissions = uiSettings.permissions[currentUser.role];
      const permissionKey = sectionToPermission[section];
      if (section !== "settings" && permissionKey && !rolePermissions[permissionKey]) {
        showMessage("Seu perfil não possui acesso a este módulo.");
        return;
      }
    }

    setActiveSection(section);
    if (section === "monitoring") {
      setActiveTab("monitoring");
    }
    if (section === "assets" || section === "dashboard") {
      setActiveTab("assets");
    }
    if (section === "reports") {
      showMessage("Relatórios abertos.");
    }
    if (section === "settings") {
      showMessage("Configurações abertas. Ajustes salvos são aplicados no sistema.");
    }
  }

  async function handleExport() {
    try {
      const assets = await listAssets();
      const csv = assetsToCsv(assets);
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `assets-${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      showMessage("Exportação concluída.");
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "Falha ao exportar ativos.");
    }
  }

  function handleOpenNewAsset() {
    setActiveSection("assets");
    setActiveTab("assets");
    window.dispatchEvent(new CustomEvent("assets:create-new"));
  }

  function handleHeaderSearch() {
    const query = headerQuery.trim();
    if (!query) {
      showMessage("Digite um termo para buscar.");
      return;
    }
    setActiveSection("assets");
    setActiveTab("assets");
    showMessage(`Filtro rápido aplicado: ${query}`);
  }

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  async function handleRefreshAll() {
    await Promise.all([refreshOperationalData(), refreshSummary()]);
    showMessage("Dados atualizados.");
  }

  function renderMainContent() {
    if (activeSection === "reports") {
      return <ReportsPanel assets={allAssets} />;
    }

    if (activeSection === "tickets") {
      return <TicketsPanel />;
    }

    if (activeSection === "commands") {
      if (currentUser.role !== "admin") {
        return (
          <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="text-2xl font-semibold text-slate-900">Acesso restrito</h3>
            <p className="mt-2 text-sm text-slate-500">Apenas o administrador tem acesso a Comandos.</p>
          </section>
        );
      }
      return <CommandsPanel monitoringItems={monitoringItems} />;
    }

    if (activeSection === "settings") {
      return (
        <SettingsPanel
          initialSettings={uiSettings}
          currentRole={currentUser.role}
          onSave={(next) => {
            setUiSettings(next);
            saveUiSettings(next);
            setActionMessage("Configurações aplicadas.");
          }}
        />
      );
    }

    if (activeSection === "monitoring" || activeTab === "monitoring") {
      return <MonitoringPanel thresholds={uiSettings.thresholds} />;
    }

    if (activeTab === "cloud" || activeTab === "discovery") {
      return (
        <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-2xl font-semibold text-slate-900">
            {activeTab === "cloud" ? "Cloud Assets" : "Discovery"}
          </h3>
          <p className="mt-2 text-sm text-slate-500">
            Painel em preparação. Os botões já direcionam corretamente para essa área.
          </p>
        </section>
      );
    }

    return <AssetsManager externalQuery={headerQuery} />;
  }

  return (
    <main className="min-h-screen bg-slate-100">
      <div className="grid min-h-screen lg:grid-cols-[260px_1fr]">
        <aside className="sticky top-0 h-screen border-r border-slate-800 bg-slate-950 text-slate-100">
          <div className="flex h-full flex-col">
            <div className="border-b border-slate-800 px-6 py-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-lg shadow-brand-900/30">
                  <MonitorSmartphone className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-slate-400">Enterprise</p>
                  <h1 className="text-lg font-semibold">IT Manager</h1>
                </div>
              </div>
            </div>

            <nav className="flex-1 space-y-2 px-4 py-5 text-sm">
              {sidebarItems.map((item) => {
                const Icon = item.icon;
                const isActive = activeSection === item.id;
                const canAccess =
                  item.id === "settings"
                    ? true
                    : item.id === "commands"
                      ? currentUser.role === "admin"
                      : uiSettings.permissions[currentUser.role][sectionToPermission[item.id]!];
                return (
                  <button
                    key={item.id}
                    onClick={() => handleSidebarClick(item.id)}
                    disabled={!canAccess}
                    className={`flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left transition ${
                      isActive
                        ? "bg-slate-800 text-white shadow-inner"
                        : "text-slate-300 hover:bg-slate-900 hover:text-white"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span className={!canAccess ? "opacity-50" : ""}>{item.label}</span>
                  </button>
                );
              })}
            </nav>

            <div className="border-t border-slate-800 p-4">
              <div className="rounded-2xl bg-slate-900/80 p-4">
                <p className="text-xs uppercase tracking-[0.25em] text-slate-400">Service Mgmt</p>
                <p className="mt-2 text-sm text-slate-300">
                  Monitoramento, auditoria e descoberta em um só lugar.
                </p>
              </div>
            </div>
          </div>
        </aside>

        <section className="min-w-0 space-y-6 p-4 lg:p-6">
          <header className="rounded-[28px] border border-slate-200 bg-white px-5 py-4 shadow-sm">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div className="flex flex-1 items-center gap-3">
                {isDashboard ? (
                  <>
                    <div className="relative w-full max-w-4xl">
                      <Search className="pointer-events-none absolute left-4 top-3.5 h-4 w-4 text-slate-400" />
                      <input
                        value={headerQuery}
                        onChange={(event) => {
                          const value = event.target.value;
                          setHeaderQuery(value);
                          if (value.trim().length > 0) {
                            setActiveSection("assets");
                            setActiveTab("assets");
                          }
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            handleHeaderSearch();
                          }
                        }}
                        placeholder="Buscar ativos por nome, tag, local ou responsável"
                        className="h-11 w-full rounded-2xl border border-slate-200 bg-slate-50 pl-10 pr-4 text-sm text-slate-700 outline-none focus:border-brand-500"
                      />
                    </div>
                    <button
                      onClick={() => void handleExport()}
                      className="hidden h-11 rounded-2xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-600 lg:inline-flex"
                    >
                      <Download className="mr-2 h-4 w-4" />
                      Exportar
                    </button>
                  </>
                ) : (
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-500">
                    {pageTitle}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => void handleRefreshAll()}
                  className="inline-flex h-11 items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-600"
                >
                  <RefreshCw className="h-4 w-4" />
                  Atualizar
                </button>
                <button
                  onClick={() => {
                    setActiveSection("monitoring");
                    setActiveTab("monitoring");
                    showMessage("Monitoramento aberto.");
                  }}
                  className="flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-500"
                >
                  <Bell className="h-4 w-4" />
                </button>
                <button
                  onClick={() => {
                    setActiveSection("settings");
                    showMessage("Configurações abertas.");
                  }}
                  className="flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-500"
                >
                  <Settings className="h-4 w-4" />
                </button>
                {isDashboard ? (
                  <button
                    onClick={handleOpenNewAsset}
                    className="inline-flex h-11 items-center gap-2 rounded-2xl bg-brand-600 px-4 text-sm font-semibold text-white shadow-lg shadow-brand-600/20"
                  >
                    <Plus className="h-4 w-4" />
                    Novo
                  </button>
                ) : null}
                <button
                  onClick={handleLogout}
                  className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-200 text-slate-500"
                  title="Sair"
                >
                  <UserCircle2 className="h-6 w-6" />
                </button>
              </div>
            </div>
          </header>

          {activeSection === "dashboard" ? (
            <section className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-sm font-medium text-brand-600">Operação diária</p>
                  <h2 className="mt-2 text-3xl font-semibold text-slate-900">Resumo operacional</h2>
                  <p className="mt-2 max-w-2xl text-sm text-slate-500">
                    Foque em alertas ativos, notebooks sem heartbeat e pendências de envio dos agentes.
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  {tabs.map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => {
                        setActiveTab(tab.id);
                        if (tab.id === "monitoring") {
                          setActiveSection("monitoring");
                        } else {
                          setActiveSection("assets");
                        }
                      }}
                      className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                        activeTab === tab.id
                          ? "bg-brand-600 text-white shadow-sm"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-3">
                <article className="rounded-2xl border border-red-200 bg-red-50 p-4">
                  <div className="flex items-center gap-2 text-red-700">
                    <TriangleAlert className="h-4 w-4" />
                    <p className="text-sm font-semibold">Alertas ativos</p>
                  </div>
                  <p className="mt-2 text-2xl font-semibold text-red-700">{operationalStats.alerts}</p>
                </article>
                <article className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                  <p className="text-sm font-semibold text-amber-700">Sem heartbeat</p>
                  <p className="mt-2 text-2xl font-semibold text-amber-700">{operationalStats.offline}</p>
                </article>
                <article className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-sm font-semibold text-slate-700">Fila pendente</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-900">{operationalStats.pendingQueue}</p>
                </article>
              </div>

              <div className="mt-5 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
                <span className="font-semibold text-slate-700">Status</span>
                <span className="text-slate-500">{actionMessage || "Clique em Atualizar para recarregar os dados críticos."}</span>
              </div>
            </section>
          ) : null}

          {activeSection === "dashboard" ? (
            <div className="space-y-4">
              <section className="grid gap-4 md:grid-cols-3">
                <article className="rounded-2xl border border-red-200 bg-red-50 p-4">
                  <div className="flex items-center gap-2 text-red-700">
                    <TriangleAlert className="h-4 w-4" />
                    <p className="text-sm font-semibold">Críticos</p>
                  </div>
                  <p className="mt-2 text-2xl font-semibold text-red-700">{dashboardAlerts.critical}</p>
                </article>
                <article className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                  <p className="text-sm font-semibold text-amber-700">Em alerta</p>
                  <p className="mt-2 text-2xl font-semibold text-amber-700">{dashboardAlerts.warning}</p>
                </article>
                <article className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-sm font-semibold text-slate-700">Sem atualização</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-900">{dashboardAlerts.stale}</p>
                  <p className="mt-1 text-xs text-slate-500">Acima de {uiSettings.thresholds.staleHours}h</p>
                </article>
              </section>

              <section className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-900">Auditorias pendentes</p>
                  <div className="flex items-center gap-2">
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
                      {summary.pending_audit} pendente(s)
                    </span>
                    {pendingAudits.length > 0 && (currentUser.role === "admin" || currentUser.role === "manager") ? (
                      <button
                        onClick={() => void handleResolveAllAudits()}
                        disabled={resolvingAllAudits}
                        className="rounded-full bg-brand-600 px-3 py-1 text-xs font-semibold text-white disabled:opacity-60"
                      >
                        {resolvingAllAudits ? "Resolvendo..." : "Resolver todas"}
                      </button>
                    ) : null}
                  </div>
                </div>
                {pendingAudits.length === 0 ? (
                  <p className="mt-3 text-sm text-slate-500">Nenhuma pendência encontrada no momento.</p>
                ) : (
                  <div className="mt-3 overflow-x-auto rounded-xl border border-slate-200">
                    <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                      <thead className="bg-slate-50 text-slate-500">
                        <tr>
                          <th className="px-3 py-2 font-medium">Ação</th>
                          <th className="px-3 py-2 font-medium">Usuário</th>
                          <th className="px-3 py-2 font-medium">Item</th>
                          <th className="px-3 py-2 font-medium">Quando</th>
                          <th className="px-3 py-2 font-medium">Ações</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {pendingAudits.map((item) => (
                          <tr key={item.id} className="hover:bg-slate-50">
                            <td className="px-3 py-2">{item.action}</td>
                            <td className="px-3 py-2">{item.actor_email || "—"}</td>
                            <td className="px-3 py-2">{item.details || item.entity_id || "—"}</td>
                            <td className="px-3 py-2">
                              {item.created_at
                                ? new Date(item.created_at).toLocaleString("pt-BR")
                                : "—"}
                            </td>
                            <td className="px-3 py-2">
                              {currentUser.role === "admin" || currentUser.role === "manager" ? (
                                <button
                                  onClick={() => void handleResolveAudit(item.id)}
                                  disabled={resolvingAuditId === item.id}
                                  className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-60"
                                >
                                  {resolvingAuditId === item.id ? "Resolvendo..." : "Resolver"}
                                </button>
                              ) : (
                                "—"
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </div>
          ) : null}

          {renderMainContent()}
        </section>
      </div>
    </main>
  );
}
