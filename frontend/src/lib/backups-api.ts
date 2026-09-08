import { getApiBaseUrlCandidates, getToken } from "@/lib/session";

export type BackupLog = {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: "em_andamento" | "sucesso" | "erro";
  file_path: string | null;
  size_bytes: number | null;
  message: string | null;
  triggered_by: "manual" | "agendado" | "seguranca_pre_importacao";
  triggered_by_email: string | null;
};

export type BackupImportResult = {
  safety_backup_id: number;
  restored: string[];
  failed: string[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const requestInit: RequestInit = {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-API-Version": "v1",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
  };

  let response: Response | null = null;
  let lastError: unknown;
  for (const baseUrl of getApiBaseUrlCandidates()) {
    try {
      response = await fetch(`${baseUrl}/api/v1/backups${path}`, requestInit);
      break;
    } catch (error) {
      lastError = error;
    }
  }

  if (!response) {
    throw new Error(lastError instanceof Error ? lastError.message : "Falha de conexão com API");
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Falha na operação de backup");
  }

  return response.json() as Promise<T>;
}

export function runBackupNow(): Promise<BackupLog> {
  return request<BackupLog>("", { method: "POST" });
}

export function listBackups(limit = 50): Promise<BackupLog[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return request<BackupLog[]>(`?${params.toString()}`);
}

export async function downloadBackup(id: number, suggestedName: string): Promise<void> {
  const token = getToken();
  let response: Response | null = null;
  let lastError: unknown;
  for (const baseUrl of getApiBaseUrlCandidates()) {
    try {
      response = await fetch(`${baseUrl}/api/v1/backups/${id}/download`, {
        headers: {
          "X-API-Version": "v1",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      break;
    } catch (error) {
      lastError = error;
    }
  }

  if (!response) {
    throw new Error(lastError instanceof Error ? lastError.message : "Falha de conexão com API");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Falha ao baixar backup");
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = suggestedName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export async function exportBackupNow(): Promise<void> {
  const log = await runBackupNow();
  const stamp = log.started_at.replace(/[-:]/g, "").replace("T", "_").slice(0, 15);
  await downloadBackup(log.id, `backup_${stamp}.zip`);
}

export async function importBackup(file: File): Promise<BackupImportResult> {
  const token = getToken();
  const formData = new FormData();
  formData.append("file", file);

  let response: Response | null = null;
  let lastError: unknown;
  for (const baseUrl of getApiBaseUrlCandidates()) {
    try {
      response = await fetch(`${baseUrl}/api/v1/backups/import`, {
        method: "POST",
        headers: {
          "X-API-Version": "v1",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: formData,
      });
      break;
    } catch (error) {
      lastError = error;
    }
  }

  if (!response) {
    throw new Error(lastError instanceof Error ? lastError.message : "Falha de conexão com API");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Falha ao importar backup");
  }

  return response.json() as Promise<BackupImportResult>;
}
