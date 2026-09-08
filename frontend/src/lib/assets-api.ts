import { getApiBaseUrlCandidates, getToken } from "@/lib/session";

export type Asset = {
  id: number;
  asset_tag: string;
  screen_asset_tag: string | null;
  name: string;
  category: string | null;
  status: string;
  serial_number: string | null;
  brand: string | null;
  model: string | null;
  location: string | null;
  owner: string | null;
  department: string | null;
  notes: string | null;
};

export type AssetPayload = {
  asset_tag: string;
  screen_asset_tag?: string | null;
  name: string;
  category?: string | null;
  status?: string | null;
  serial_number?: string | null;
  brand?: string | null;
  model?: string | null;
  location?: string | null;
  owner?: string | null;
  department?: string | null;
  notes?: string | null;
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
      response = await fetch(`${baseUrl}/api/v1/assets${path}`, requestInit);
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
    throw new Error(payload.detail || "Falha na operação");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function listAssets(): Promise<Asset[]> {
  return request<Asset[]>("");
}

export function createAsset(payload: AssetPayload): Promise<Asset> {
  return request<Asset>("", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAsset(id: number, payload: AssetPayload): Promise<Asset> {
  return request<Asset>(`/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteAsset(id: number): Promise<void> {
  return request<void>(`/${id}`, {
    method: "DELETE",
  });
}
