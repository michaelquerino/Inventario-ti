"use client";

import { DatabaseBackup, Download, Save, Upload } from "lucide-react";
import type { ChangeEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { isSingleAdminMode } from "@/lib/auth-config";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  downloadBackup,
  exportBackupNow,
  importBackup,
  listBackups,
  runBackupNow,
  type BackupLog,
} from "@/lib/backups-api";

import {
  defaultUiSettings,
  type PermissionsSettings,
  type ThresholdSettings,
  type UiSettings,
} from "@/lib/ui-config";

type SettingsPanelProps = {
  initialSettings: UiSettings;
  currentRole: "admin" | "manager" | "viewer";
  onSave: (settings: UiSettings) => void;
};

const roles: Array<"admin" | "manager" | "viewer"> = ["admin", "manager", "viewer"];
const modules: Array<keyof PermissionsSettings["admin"]> = [
  "dashboard",
  "assets",
  "monitoring",
  "reports",
  "tickets",
  "settings",
];

const backupStatusLabel: Record<BackupLog["status"], string> = {
  em_andamento: "Em andamento",
  sucesso: "Sucesso",
  erro: "Erro",
};

const backupStatusClass: Record<BackupLog["status"], string> = {
  em_andamento: "bg-amber-100 text-amber-700",
  sucesso: "bg-emerald-100 text-emerald-700",
  erro: "bg-red-100 text-red-700",
};

const backupOrigemLabel: Record<BackupLog["triggered_by"], string> = {
  manual: "manual",
  agendado: "agendado",
  seguranca_pre_importacao: "segurança pré-importação",
};

function formatBytes(bytes: number | null): string {
  if (!bytes) return "—";
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(bytes / 1024).toFixed(0)} KB`;
}

export function SettingsPanel({ initialSettings, currentRole, onSave }: SettingsPanelProps) {
  const singleAdminMode = isSingleAdminMode();
  const [thresholds, setThresholds] = useState<ThresholdSettings>(initialSettings.thresholds);
  const [permissions, setPermissions] = useState<PermissionsSettings>(initialSettings.permissions);
  const [message, setMessage] = useState("");

  const [backups, setBackups] = useState<BackupLog[]>([]);
  const [backupsCarregando, setBackupsCarregando] = useState(false);
  const [executandoBackup, setExecutandoBackup] = useState(false);
  const [exportandoBackup, setExportandoBackup] = useState(false);
  const [importandoBackup, setImportandoBackup] = useState(false);
  const [arquivoParaImportar, setArquivoParaImportar] = useState<File | null>(null);
  const [backupErro, setBackupErro] = useState("");
  const [backupMensagem, setBackupMensagem] = useState("");
  const importInputRef = useRef<HTMLInputElement>(null);

  const canEditPermissions = useMemo(() => currentRole === "admin", [currentRole]);
  const isAdmin = currentRole === "admin";

  async function refreshBackups() {
    setBackupsCarregando(true);
    try {
      const dados = await listBackups(50);
      setBackups(dados);
    } catch (err) {
      setBackupErro(err instanceof Error ? err.message : "Erro ao carregar histórico de backups");
    } finally {
      setBackupsCarregando(false);
    }
  }

  useEffect(() => {
    if (isAdmin) {
      void refreshBackups();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  async function handleRunBackup() {
    setBackupErro("");
    setBackupMensagem("");
    setExecutandoBackup(true);
    try {
      await runBackupNow();
      setBackupMensagem("Backup concluído com sucesso.");
      await refreshBackups();
    } catch (err) {
      setBackupErro(err instanceof Error ? err.message : "Erro ao executar backup");
    } finally {
      setExecutandoBackup(false);
    }
  }

  async function handleDownloadBackup(log: BackupLog) {
    setBackupErro("");
    try {
      const nomeArquivo = log.file_path ? log.file_path.split(/[\\/]/).pop() || `backup-${log.id}.zip` : `backup-${log.id}.zip`;
      await downloadBackup(log.id, nomeArquivo);
    } catch (err) {
      setBackupErro(err instanceof Error ? err.message : "Erro ao baixar backup");
    }
  }

  async function handleExportBackup() {
    setBackupErro("");
    setBackupMensagem("");
    setExportandoBackup(true);
    try {
      await exportBackupNow();
      setBackupMensagem("Backup exportado e baixado com sucesso.");
      await refreshBackups();
    } catch (err) {
      setBackupErro(err instanceof Error ? err.message : "Erro ao exportar backup");
    } finally {
      setExportandoBackup(false);
    }
  }

  function handleImportClick() {
    importInputRef.current?.click();
  }

  function handleImportFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setArquivoParaImportar(file);
  }

  async function handleConfirmarImportacao() {
    if (!arquivoParaImportar) return;
    const file = arquivoParaImportar;

    setBackupErro("");
    setBackupMensagem("");
    setImportandoBackup(true);
    try {
      const resultado = await importBackup(file);
      if (resultado.failed.length > 0) {
        setBackupErro(`Restaurado parcialmente. Falhas: ${resultado.failed.join("; ")}`);
      } else {
        setBackupMensagem(`Backup importado com sucesso (${resultado.restored.join(", ")}).`);
      }
      setArquivoParaImportar(null);
      await refreshBackups();
    } catch (err) {
      setBackupErro(err instanceof Error ? err.message : "Erro ao importar backup");
    } finally {
      setImportandoBackup(false);
    }
  }

  function updateThreshold(key: keyof ThresholdSettings, value: string) {
    const numeric = Number(value);
    if (Number.isNaN(numeric)) return;
    setThresholds((prev) => ({ ...prev, [key]: numeric }));
  }

  function togglePermission(role: "admin" | "manager" | "viewer", moduleName: keyof PermissionsSettings["admin"]) {
    if (!canEditPermissions) return;
    setPermissions((prev) => ({
      ...prev,
      [role]: {
        ...prev[role],
        [moduleName]: !prev[role][moduleName],
      },
    }));
  }

  function handleSave() {
    const merged: UiSettings = {
      thresholds: {
        ...defaultUiSettings.thresholds,
        ...thresholds,
      },
      permissions: {
        admin: { ...defaultUiSettings.permissions.admin, ...permissions.admin },
        manager: { ...defaultUiSettings.permissions.manager, ...permissions.manager },
        viewer: { ...defaultUiSettings.permissions.viewer, ...permissions.viewer },
      },
    };
    onSave(merged);
    setMessage("Configurações salvas com sucesso.");
  }

  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="text-2xl font-semibold text-slate-900">Configurações</h3>
          <p className="mt-1 text-sm text-slate-500">
            Gerencie limiares de alerta operacionais. Ao salvar, as mudanças são aplicadas imediatamente.
          </p>
        </div>
        <button
          onClick={handleSave}
          className="inline-flex items-center gap-2 rounded-2xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white"
        >
          <Save className="h-4 w-4" />
          Salvar
        </button>
      </div>

      {message ? <p className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</p> : null}

      <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <label className="space-y-1 text-sm text-slate-700">
          <span>CPU alerta (%)</span>
          <input
            type="number"
            value={thresholds.cpuWarn}
            onChange={(event) => updateThreshold("cpuWarn", event.target.value)}
            className="h-10 w-full rounded-xl border border-slate-200 px-3"
          />
        </label>
        <label className="space-y-1 text-sm text-slate-700">
          <span>CPU crítico (%)</span>
          <input
            type="number"
            value={thresholds.cpuCritical}
            onChange={(event) => updateThreshold("cpuCritical", event.target.value)}
            className="h-10 w-full rounded-xl border border-slate-200 px-3"
          />
        </label>
        <label className="space-y-1 text-sm text-slate-700">
          <span>RAM alerta (%)</span>
          <input
            type="number"
            value={thresholds.ramWarn}
            onChange={(event) => updateThreshold("ramWarn", event.target.value)}
            className="h-10 w-full rounded-xl border border-slate-200 px-3"
          />
        </label>
        <label className="space-y-1 text-sm text-slate-700">
          <span>RAM crítico (%)</span>
          <input
            type="number"
            value={thresholds.ramCritical}
            onChange={(event) => updateThreshold("ramCritical", event.target.value)}
            className="h-10 w-full rounded-xl border border-slate-200 px-3"
          />
        </label>
        <label className="space-y-1 text-sm text-slate-700">
          <span>Disco alerta (%)</span>
          <input
            type="number"
            value={thresholds.diskWarn}
            onChange={(event) => updateThreshold("diskWarn", event.target.value)}
            className="h-10 w-full rounded-xl border border-slate-200 px-3"
          />
        </label>
        <label className="space-y-1 text-sm text-slate-700">
          <span>Disco crítico (%)</span>
          <input
            type="number"
            value={thresholds.diskCritical}
            onChange={(event) => updateThreshold("diskCritical", event.target.value)}
            className="h-10 w-full rounded-xl border border-slate-200 px-3"
          />
        </label>
        <label className="space-y-1 text-sm text-slate-700">
          <span>Sem atualização (horas)</span>
          <input
            type="number"
            value={thresholds.staleHours}
            onChange={(event) => updateThreshold("staleHours", event.target.value)}
            className="h-10 w-full rounded-xl border border-slate-200 px-3"
          />
        </label>
      </div>

      {isAdmin ? (
        <div className="mt-6 rounded-2xl border border-slate-200">
          <div className="flex items-center justify-between gap-4 border-b border-slate-200 bg-slate-50 px-4 py-3">
            <div>
              <p className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <DatabaseBackup className="h-4 w-4" />
                Backup do banco de dados
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Backup automático roda em segundo plano no servidor. Também é possível disparar, exportar ou
                restaurar um manualmente.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => void handleRunBackup()}
                disabled={executandoBackup}
                className="inline-flex items-center gap-2 rounded-2xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
              >
                <DatabaseBackup className="h-4 w-4" />
                {executandoBackup ? "Executando..." : "Fazer backup agora"}
              </button>
              <button
                onClick={() => void handleExportBackup()}
                disabled={exportandoBackup}
                className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-60"
              >
                <Download className="h-4 w-4" />
                {exportandoBackup ? "Exportando..." : "Exportar backup"}
              </button>
              <button
                onClick={handleImportClick}
                disabled={importandoBackup}
                className="inline-flex items-center gap-2 rounded-2xl border border-amber-300 px-4 py-2 text-sm font-semibold text-amber-800 disabled:opacity-60"
              >
                <Upload className="h-4 w-4" />
                {importandoBackup ? "Importando..." : "Importar backup"}
              </button>
              <input
                ref={importInputRef}
                type="file"
                accept=".zip"
                className="hidden"
                onChange={handleImportFileSelected}
              />
            </div>
          </div>

          <div className="px-4 py-3">
            {backupErro ? <p className="mb-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{backupErro}</p> : null}
            {backupMensagem ? (
              <p className="mb-3 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{backupMensagem}</p>
            ) : null}

            {backupsCarregando ? (
              <p className="text-sm text-slate-500">Carregando histórico...</p>
            ) : backups.length === 0 ? (
              <p className="text-sm text-slate-500">Nenhum backup registrado ainda.</p>
            ) : (
              <div className="max-h-72 space-y-2 overflow-auto">
                {backups.map((log) => (
                  <div
                    key={log.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 px-3 py-2 text-sm"
                  >
                    <div>
                      <span className="font-medium text-slate-900">
                        {new Date(log.started_at).toLocaleString("pt-BR")}
                      </span>
                      <span className="ml-2 text-xs text-slate-400">
                        {backupOrigemLabel[log.triggered_by]}
                        {log.triggered_by_email ? ` · ${log.triggered_by_email}` : ""} · {formatBytes(log.size_bytes)}
                      </span>
                      {log.status === "erro" && log.message ? (
                        <p className="mt-1 text-xs text-red-600">{log.message}</p>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-semibold ${backupStatusClass[log.status]}`}
                      >
                        {backupStatusLabel[log.status]}
                      </span>
                      {log.status === "sucesso" ? (
                        <button
                          onClick={() => void handleDownloadBackup(log)}
                          className="inline-flex items-center gap-1 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700"
                        >
                          <Download className="h-3.5 w-3.5" />
                          Baixar
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : null}

      {singleAdminMode ? (
        <p className="mt-6 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          Modo single-admin ativo: gestao de perfis e permissoes oculta para simplificar a operacao.
        </p>
      ) : (
        <>
          <div className="mt-6 rounded-2xl border border-slate-200">
            <div className="border-b border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700">
              Permissões por perfil
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-white text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Perfil</th>
                    {modules.map((moduleName) => (
                      <th key={moduleName} className="px-4 py-3 font-medium capitalize">
                        {moduleName}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {roles.map((role) => (
                    <tr key={role}>
                      <td className="px-4 py-3 font-semibold uppercase text-slate-700">{role}</td>
                      {modules.map((moduleName) => (
                        <td key={`${role}-${moduleName}`} className="px-4 py-3">
                          <label className="inline-flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={permissions[role][moduleName]}
                              onChange={() => togglePermission(role, moduleName)}
                              disabled={!canEditPermissions}
                            />
                            <span>{permissions[role][moduleName] ? "Permitido" : "Negado"}</span>
                          </label>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {!canEditPermissions ? (
            <p className="mt-3 text-xs text-amber-700">Somente administradores podem alterar permissões.</p>
          ) : null}
        </>
      )}

      <ConfirmDialog
        open={arquivoParaImportar !== null}
        tone="danger"
        title="Restaurar backup?"
        confirmLabel={importandoBackup ? "Importando..." : "Sim, sobrescrever e restaurar"}
        confirming={importandoBackup}
        onCancel={() => setArquivoParaImportar(null)}
        onConfirm={() => void handleConfirmarImportacao()}
        description={
          arquivoParaImportar ? (
            <div className="space-y-2">
              <p>
                Isso vai <strong>sobrescrever</strong> os dados atuais do sistema com o conteúdo de{" "}
                <strong>{arquivoParaImportar.name}</strong>.
              </p>
              <p>
                Um backup de segurança do estado atual é feito automaticamente antes, mas essa ação não pode ser
                desfeita sem restaurar esse backup de segurança manualmente.
              </p>
            </div>
          ) : null
        }
      />
    </section>
  );
}
