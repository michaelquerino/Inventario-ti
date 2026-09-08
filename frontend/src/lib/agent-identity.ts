export type AgentIdentity = {
  numero_serie: string | null;
  usuario: string | null;
  patrimonio: string | null;
  patrimonio_monitor: string | null;
};

// Porta fixa do servidor HTTP local exposto pelo agente (só em 127.0.0.1,
// ver agente_identidade_http.py) -- é assim que a página descobre sozinha em
// qual notebook está sendo aberta, sem pedir login.
const AGENT_IDENTITY_URL = "http://127.0.0.1:18763/identidade";
const TIMEOUT_MS = 1500;

export async function getAgentIdentity(): Promise<AgentIdentity | null> {
  if (typeof window === "undefined") return null;

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(AGENT_IDENTITY_URL, { signal: controller.signal });
    if (!response.ok) return null;
    return (await response.json()) as AgentIdentity;
  } catch {
    // Agente não instalado nesta máquina, ou não está rodando -- fallback
    // manual assume o controle na página.
    return null;
  } finally {
    window.clearTimeout(timeout);
  }
}
