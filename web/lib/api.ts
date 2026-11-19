// Server-side access to the research API. Browser code calls /api/* instead (see next.config.ts).

import type { Run } from "./types";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Research API returned ${res.status} for ${path}`);
  return res.json() as Promise<T>;
}

export const getRun = (id: string) => get<Run>(`/research/${encodeURIComponent(id)}`);
export const listRuns = (limit = 12) => get<Run[]>(`/research?limit=${limit}`);
