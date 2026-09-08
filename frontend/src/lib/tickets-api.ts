import { getApiBaseUrlCandidates, getToken } from "@/lib/session";

export type Ticket = {
  id: number;
  numero_serie: string | null;
  usuario: string | null;
  patrimonio: string | null;
  titulo: string;
  descricao: string;
  categoria: string | null;
  status: "aberto" | "em_andamento" | "concluido";
  resposta: string | null;
  respondido_por: string | null;
  criado_em: string;
  atualizado_em: string | null;
};

export type TicketCreatePayload = {
  numero_serie?: string | null;
  usuario?: string | null;
  patrimonio?: string | null;
  titulo: string;
  descricao: string;
  categoria?: string | null;
};

export type TicketUpdatePayload = {
  status?: Ticket["status"];
  resposta?: string;
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
      response = await fetch(`${baseUrl}/api/v1/tickets${path}`, requestInit);
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
    throw new Error(payload.detail || "Falha na operação de chamados");
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

// Sem token: essa chamada precisa funcionar pra qualquer funcionário abrindo
// a página, sem estar logado no sistema.
export function createTicket(payload: TicketCreatePayload): Promise<Ticket> {
  return request<Ticket>("", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listTickets(status?: string): Promise<Ticket[]> {
  const params = status ? `?status_filtro=${encodeURIComponent(status)}` : "";
  return request<Ticket[]>(params);
}

export function updateTicket(id: number, payload: TicketUpdatePayload): Promise<Ticket> {
  return request<Ticket>(`/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
