import { AlertItem, Brief, ForecastCard, RuleCard, RuleDetail, Session, SourceRef } from "./types";

const API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

let sessionToken: string | null = null;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (sessionToken) {
    headers.set("X-Session-Token", sessionToken);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function login(email: string, name: string): Promise<Session> {
  const session = await request<Session>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, name })
  });
  sessionToken = session.token;
  return session;
}

export function listRules(): Promise<RuleCard[]> {
  return request<RuleCard[]>("/api/rules");
}

export function getRule(id: number): Promise<RuleDetail> {
  return request<RuleDetail>(`/api/rules/${id}`);
}

export function investigateRule(id: number): Promise<unknown> {
  return request(`/api/rules/${id}/investigate`, { method: "POST" });
}

export function getBrief(id: number): Promise<Brief> {
  return request<Brief>(`/api/rules/${id}/brief`);
}

export function getSources(id: number): Promise<SourceRef[]> {
  return request<SourceRef[]>(`/api/rules/${id}/sources`);
}

export function getForecasts(ruleId?: number): Promise<ForecastCard[]> {
  return request<ForecastCard[]>(ruleId ? `/api/forecasts?rule_id=${ruleId}` : "/api/forecasts");
}

export function submitForecast(id: number, probability: number): Promise<unknown> {
  return request(`/api/forecasts/${id}/position`, {
    method: "POST",
    body: JSON.stringify({ probability, rationale: "Mobile forecast" })
  });
}

export function addWatch(kind: string, value: string): Promise<unknown> {
  return request("/api/watchlists", {
    method: "POST",
    body: JSON.stringify({ kind, value })
  });
}

export function getAlerts(): Promise<AlertItem[]> {
  return request<AlertItem[]>("/api/alerts");
}
