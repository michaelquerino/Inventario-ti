import { getApiBaseUrlCandidates } from "@/lib/session";

export type RegisterPayload = {
  email: string;
  full_name: string;
  password: string;
};

export async function login(email: string, password: string): Promise<string> {
  const requestInit: RequestInit = {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Version": "v1",
    },
    body: JSON.stringify({ email, password }),
  };

  let response: Response | null = null;
  let lastError: unknown;
  for (const baseUrl of getApiBaseUrlCandidates()) {
    try {
      response = await fetch(`${baseUrl}/api/v1/auth/login`, requestInit);
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
    throw new Error(payload.detail || "Falha no login");
  }

  const payload: { access_token: string } = await response.json();
  return payload.access_token;
}

export async function register(payload: RegisterPayload): Promise<void> {
  const requestInit: RequestInit = {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Version": "v1",
    },
    body: JSON.stringify(payload),
  };

  let response: Response | null = null;
  let lastError: unknown;
  for (const baseUrl of getApiBaseUrlCandidates()) {
    try {
      response = await fetch(`${baseUrl}/api/v1/auth/register`, requestInit);
      break;
    } catch (error) {
      lastError = error;
    }
  }

  if (!response) {
    throw new Error(lastError instanceof Error ? lastError.message : "Falha de conexão com API");
  }

  if (!response.ok) {
    const responsePayload = await response.json().catch(() => ({}));
    throw new Error(responsePayload.detail || "Falha no cadastro");
  }
}
