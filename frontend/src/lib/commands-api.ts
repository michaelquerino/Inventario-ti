import { getApiBaseUrlCandidates, getToken } from "@/lib/session";

export type RemoteCommand = {
  id: number;
  numero_serie: string;
  comando: string;
  status: "pendente" | "executando" | "concluido" | "erro";
  resultado: string | null;
  codigo_saida: number | null;
  criado_por: string | null;
  criado_em: string;
  executado_em: string | null;
  agendado_para: string | null;
  modo: "usuario" | "admin";
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
      response = await fetch(`${baseUrl}/api/v1/commands${path}`, requestInit);
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
    throw new Error(payload.detail || "Falha na operação de comandos");
  }

  return response.json() as Promise<T>;
}

export function createCommand(
  numeroSeries: string[],
  comando: string,
  agendadoPara?: string,
  modo: "usuario" | "admin" = "usuario",
): Promise<RemoteCommand[]> {
  return request<RemoteCommand[]>("", {
    method: "POST",
    body: JSON.stringify({
      numero_series: numeroSeries,
      comando,
      agendado_para: agendadoPara || undefined,
      modo,
    }),
  });
}

export function listCommands(numeroSerie?: string, limit = 100): Promise<RemoteCommand[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (numeroSerie) params.set("numero_serie", numeroSerie);
  return request<RemoteCommand[]>(`?${params.toString()}`);
}

export async function deleteCommand(id: number): Promise<void> {
  const token = getToken();
  let response: Response | null = null;
  let lastError: unknown;
  for (const baseUrl of getApiBaseUrlCandidates()) {
    try {
      response = await fetch(`${baseUrl}/api/v1/commands/${id}`, {
        method: "DELETE",
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
    throw new Error(payload.detail || "Falha ao excluir comando");
  }
}

export function cancelCommand(id: number): Promise<RemoteCommand> {
  return request<RemoteCommand>(`/${id}/cancel`, { method: "PATCH" });
}

export async function getAgentUpdateScript(): Promise<string> {
  const data = await request<{ script: string }>("/agent-update-script");
  return data.script;
}

export type CommandTemplate = {
  id: number;
  nome: string;
  comando: string;
  criado_por: string | null;
  criado_em: string;
};

export function createCommandTemplate(nome: string, comando: string): Promise<CommandTemplate> {
  return request<CommandTemplate>("/templates", {
    method: "POST",
    body: JSON.stringify({ nome, comando }),
  });
}

export function listCommandTemplates(): Promise<CommandTemplate[]> {
  return request<CommandTemplate[]>("/templates");
}

export async function deleteCommandTemplate(id: number): Promise<void> {
  const token = getToken();
  let response: Response | null = null;
  let lastError: unknown;
  for (const baseUrl of getApiBaseUrlCandidates()) {
    try {
      response = await fetch(`${baseUrl}/api/v1/commands/templates/${id}`, {
        method: "DELETE",
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
    throw new Error(payload.detail || "Falha ao excluir comando salvo");
  }
}
