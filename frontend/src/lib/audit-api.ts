import { getApiBaseUrl, getToken } from "@/lib/session";

export type AuditEvent = {
  id: number;
  actor_email: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: string | null;
  created_at: string | null;
};

async function requestAudit<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const response = await fetch(`${getApiBaseUrl()}/api/v1/audit${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-API-Version": "v1",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Falha ao consultar auditoria");
  }

  return response.json() as Promise<T>;
}

export function listPendingAudits(limit = 5): Promise<AuditEvent[]> {
  return requestAudit<AuditEvent[]>(`/pending?limit=${encodeURIComponent(String(limit))}`);
}

export function resolvePendingAudit(eventId: number): Promise<{ status: string; event_id: number }> {
  return requestAudit(`/pending/${eventId}/resolve`, { method: "POST" });
}

export function resolveAllPendingAudits(): Promise<{ status: string; total: number }> {
  return requestAudit(`/pending/resolve-all`, { method: "POST" });
}
