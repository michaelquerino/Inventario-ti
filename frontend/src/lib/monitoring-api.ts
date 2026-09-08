import { getApiBaseUrlCandidates, getToken } from "@/lib/session";

export type MonitoringItem = {
  numero_serie: string;
  modelo: string;
  usuario: string;
  localizacao: string;
  uso_cpu_percent: number;
  uso_memoria_percent: number;
  memoria_total_gb: number;
  memoria_usada_gb: number;
  uso_disco_percent: number;
  armazenamento_total_gb: number;
  armazenamento_usado_gb: number;
  armazenamento_livre_gb: number;
  ultima_atualizacao: string;
  online_status: "online" | "offline";
  fila_pendente_local: number;
};

export type MonitoringVinculoPayload = {
  usuario?: string;
  localizacao?: string;
  patrimonio?: string;
  modelo_monitor?: string;
  patrimonio_monitor?: string;
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
      response = await fetch(`${baseUrl}/api/v1/monitoring${path}`, requestInit);
      break;
    } catch (error) {
      lastError = error;
    }
  }

  if (!response) {
    throw new Error(lastError instanceof Error ? lastError.message : "Falha de conexão com monitoramento");
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Falha ao atualizar monitoramento");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function listMonitoring(): Promise<MonitoringItem[]> {
  return request<MonitoringItem[]>("");
}

export function updateMonitoringVinculo(
  numeroSerie: string,
  payload: MonitoringVinculoPayload,
): Promise<{ status: string }> {
  return request<{ status: string }>(`/${encodeURIComponent(numeroSerie)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}
