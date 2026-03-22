import type {
  Entity,
  ConnectionsResponse,
  BriefingResponse,
  SearchResponse,
  GraphResponse,
  ConfigEntry,
} from './types';

const API_BASE = '/api';

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });

  if (!res.ok) {
    throw new ApiError(
      `API request failed: ${res.status} ${res.statusText}`,
      res.status
    );
  }

  return res.json() as Promise<T>;
}

export async function getEntity(slug: string): Promise<Entity> {
  return apiFetch<Entity>(`/entities/${encodeURIComponent(slug)}`);
}

export async function getConnections(
  slug: string,
  params?: { type?: string; limit?: number; offset?: number }
): Promise<ConnectionsResponse> {
  const searchParams = new URLSearchParams();
  if (params?.type) searchParams.set('type', params.type);
  if (params?.limit != null) searchParams.set('limit', String(params.limit));
  if (params?.offset != null) searchParams.set('offset', String(params.offset));
  const qs = searchParams.toString();
  return apiFetch<ConnectionsResponse>(
    `/entities/${encodeURIComponent(slug)}/connections${qs ? `?${qs}` : ''}`
  );
}

export async function getBriefing(slug: string): Promise<BriefingResponse> {
  return apiFetch<BriefingResponse>(
    `/entities/${encodeURIComponent(slug)}/briefing`
  );
}

export async function searchEntities(
  q: string,
  type?: string
): Promise<SearchResponse> {
  const searchParams = new URLSearchParams({ q });
  if (type) searchParams.set('type', type);
  return apiFetch<SearchResponse>(`/search?${searchParams.toString()}`);
}

export async function getGraph(
  slug: string,
  depth?: number
): Promise<GraphResponse> {
  const searchParams = new URLSearchParams();
  if (depth != null) searchParams.set('depth', String(depth));
  const qs = searchParams.toString();
  return apiFetch<GraphResponse>(
    `/graph/${encodeURIComponent(slug)}${qs ? `?${qs}` : ''}`
  );
}

export async function getConfig(): Promise<ConfigEntry[]> {
  return apiFetch<ConfigEntry[]>('/config');
}

export async function setConfigValue(key: string, value: string): Promise<void> {
  await apiFetch(`/config/${encodeURIComponent(key)}`, {
    method: 'POST',
    body: JSON.stringify({ value }),
  });
}

export async function clearConfigValue(key: string): Promise<void> {
  await apiFetch(`/config/${encodeURIComponent(key)}`, {
    method: 'DELETE',
  });
}

export { ApiError };
