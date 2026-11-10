import { API_URL } from "@/lib/config";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const TOKEN_KEY = "bvmt-token";

export function getToken(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, `API injoignable (${API_URL}). Vérifiez que le serveur est démarré.`);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join(" ; ");
    } catch {
      /* keep the status text */
    }
    throw new ApiError(response.status, detail);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body === undefined ? undefined : JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

// ---------------------------------------------------------------- market
export interface Mover {
  ticker: string;
  name: string;
  sector: string;
  close: number;
  change_pct: number;
  volume: number;
  turnover: number;
}

export interface Overview {
  session: string;
  index: { name: string; note: string; value: number; change_pct: number; history: { date: string; value: number }[] };
  breadth: { listed: number; traded: number; advancing: number; declining: number; unchanged: number };
  totals: { volume: number; turnover: number; trades: number };
  gainers: Mover[];
  losers: Mover[];
  most_active: Mover[];
  volume_history: { date: string; volume: number; turnover: number }[];
}

export interface Quote extends Mover {
  open: number;
  high: number;
  low: number;
  trades: number;
  traded: boolean;
  previous_close: number | null;
}

export interface StockSummary {
  ticker: string;
  isin: string;
  name: string;
  sector: string;
  market_group: number;
  last_close: number;
  listed: boolean;
}

export interface HistoryRow {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  traded: boolean;
  rsi: number | null;
  macd: number | null;
  signal: number | null;
  histogram: number | null;
  bb_middle: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  sma_20: number | null;
  sma_50: number | null;
}

export interface StockDetail {
  ticker: string;
  isin: string;
  name: string;
  sector: string;
  listed: boolean;
  first_session: string;
  last_session: string;
  quote: {
    session: string;
    close: number;
    previous_close: number;
    change_pct: number;
    volume: number;
    turnover: number;
    traded: boolean;
  };
  indicators: {
    rsi: number | null;
    macd: number | null;
    macd_signal: number | null;
    macd_histogram: number | null;
    bb_upper: number | null;
    bb_lower: number | null;
    bb_percent_b: number | null;
    sma_20: number | null;
    sma_50: number | null;
  };
  history: HistoryRow[];
}

// ---------------------------------------------------------------- accounts
export interface User {
  id: number;
  email: string;
  username: string;
  risk_profile: "conservative" | "moderate" | "aggressive";
  email_alerts: boolean;
}

export interface AuthResponse {
  access_token: string;
  user: User;
}
