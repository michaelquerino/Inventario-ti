const TOKEN_KEY = "inventario_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

export function getApiBaseUrl(): string {
  const rawUrl = process.env.NEXT_PUBLIC_API_URL?.trim();

  if (rawUrl) {
    const normalizedUrl = rawUrl.replace(/\s+/g, "").replace(/\/$/, "");
    try {
      const parsedUrl = new URL(normalizedUrl);
      return `${parsedUrl.protocol}//${parsedUrl.host}`;
    } catch {
      // ignora URL inválida e cai no fallback abaixo
    }
  }

  // Sem override explícito: o backend roda no mesmo host do frontend, só que
  // na porta 8000. Deriva do hostname que o navegador realmente usou pra
  // acessar a página -- funciona em localhost, IP da LAN ou VPN, sem precisar
  // fixar um IP que muda com o tempo.
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }

  return "http://localhost:8000";
}

export function getApiBaseUrlCandidates(): string[] {
  const base = getApiBaseUrl();
  const candidates = [base];

  try {
    const parsed = new URL(base);
    const isLocalhost = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
    if (isLocalhost) {
      const alternateProtocol = parsed.protocol === "https:" ? "http:" : "https:";
      candidates.push(`${alternateProtocol}//${parsed.host}`);
    }
  } catch {
    return ["http://localhost:8000", "https://localhost:8000"];
  }

  return [...new Set(candidates)];
}
