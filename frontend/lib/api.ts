import { API_URL } from "@/lib/config";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(inFrench(message));
    this.status = status;
  }
}

/** The API speaks English; the messages a user can cause are shown in French. */
const MESSAGES: [RegExp, (...groups: string[]) => string][] = [
  [
    /^not enough cash: the order costs ([\d.]+) TND, ([\d.-]+) TND available$/,
    (cost, cash) => `Liquidités insuffisantes : l’ordre coûte ${cost} TND, ${cash} TND disponibles.`,
  ],
  [/^cannot sell (\d+) (\S+): (\d+) held$/, (n, t, held) => `Impossible de vendre ${n} ${t} : ${held} en portefeuille.`],
  [/^(\S+) is no longer listed$/, (t) => `${t} n’est plus cotée.`],
  [/^unknown stock: (.+)$/, (t) => `Valeur inconnue : ${t}.`],
  [/^wrong e-mail address or password$/, () => "Adresse e-mail ou mot de passe incorrect."],
  [/^an account already uses this e-mail address$/, () => "Un compte utilise déjà cette adresse e-mail."],
  [/^sign in to use this feature$/, () => "Connectez-vous pour utiliser cette fonction."],
  [
    /needs at least (\d+) sessions, found (\d+)$/,
    (need, found) => `Historique trop court pour une prévision : ${found} séances, ${need} nécessaires.`,
  ],
];

function inFrench(message: string): string {
  for (const [pattern, render] of MESSAGES) {
    const match = message.match(pattern);
    if (match) return render(...match.slice(1));
  }
  return message;
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

// ---------------------------------------------------------------- forecast
export interface AdfResult {
  statistic: number | null;
  p_value: number | null;
  lags: number | null;
  stationary: boolean | null;
}

export interface BacktestScore {
  rmse: number | null;
  mae: number | null;
  directional_accuracy: number | null;
  origins: number;
}

export interface Forecast {
  ticker: string;
  last_session: string;
  last_close: number;
  horizon: number;
  model: { selected: "arima" | "ema" | "naive"; arima_order: number[]; beats_random_walk: boolean };
  expected_return_pct: number;
  daily_volatility_pct: number;
  forecast: { date: string; price: number; lower80: number; upper80: number; lower95: number; upper95: number }[];
  diagnostics: {
    adf_log_price: AdfResult;
    adf_log_returns: AdfResult;
    candidates: { order: number[]; aic: number; bic: number }[];
    selected_by_aic: number[] | null;
    selected_by_bic: number[] | null;
  };
  backtest: {
    span_sessions: number;
    step_sessions: number;
    horizon: number;
    models: Record<"arima" | "ema" | "naive", BacktestScore>;
  };
  volume: {
    expected: number;
    lower80: number;
    upper80: number;
    average_20_sessions: number;
    traded_probability: number | null;
  };
}

// ---------------------------------------------------------------- anomalies
export interface MarketAlert {
  date: string;
  ticker: string;
  name: string;
  sector: string;
  close: number;
  volume: number;
  change_pct: number | null;
  volume_z: number | null;
  kinds: ("volume_spike" | "price_move" | "pattern" | "corporate_action")[];
  severity: "low" | "medium" | "high" | "critical";
  score: number;
  message: string;
}

export interface AlertsResponse {
  session: string;
  scanned_sessions: number;
  total: number;
  by_severity: Record<MarketAlert["severity"], number>;
  alerts: MarketAlert[];
}

// ---------------------------------------------------------------- portfolio
export type RiskProfile = User["risk_profile"];

export interface ProfileQuestions {
  questions: Record<string, string[]>;
  profiles: Record<RiskProfile, { risk_aversion: number; max_weight: number }>;
}

export interface RiskMetrics {
  annual_return_pct: number | null;
  volatility_pct: number | null;
  sharpe: number | null;
  max_drawdown_pct: number | null;
  var95_pct: number | null;
  cvar95_pct: number | null;
  var95_tnd: number | null;
}

export interface StressTest {
  name: "worst_20_sessions" | "worst_session" | "market_minus_10" | "largest_sector_minus_15";
  kind: "historical" | "hypothetical";
  from?: string;
  to?: string;
  sector?: string;
  sector_weight_pct?: number;
  market_pct: number;
  portfolio_pct: number;
}

export interface Holding {
  ticker: string;
  name: string;
  sector: string;
  last_close: number;
  weight_pct: number;
  expected_return_pct: number;
  volatility_pct: number;
  return_contribution_pct: number;
  risk_share_pct: number;
  reason: "diversifier" | "return_driver" | "core";
  shares?: number;
  amount_tnd?: number;
}

export interface Recommendation {
  profile: RiskProfile;
  session: string;
  universe: { stocks: number; lookback_sessions: number };
  assumptions: { risk_aversion: number; max_weight: number; risk_free_rate: number; mean_shrinkage: number };
  expected: { return_pct: number; volatility_pct: number; sharpe: number | null };
  holdings: Holding[];
  in_sample: RiskMetrics;
  out_of_sample: {
    chosen_on: [string, string];
    scored_on: [string, string];
    portfolio: RiskMetrics;
    equal_weight: RiskMetrics;
  } | null;
  history: { date: string; value: number }[];
  frontier: { risk_aversion: number; volatility_pct: number; return_pct: number }[];
  stress_tests: StressTest[];
}

export interface AccountPosition {
  ticker: string;
  name: string;
  sector: string;
  quantity: number;
  avg_cost: number;
  last_close: number;
  market_value: number;
  pnl: number;
  pnl_pct: number;
  weight_pct: number;
}

export interface Account {
  session: string;
  initial_capital: number;
  cash: number;
  invested: number;
  total_value: number;
  pnl: number;
  pnl_pct: number;
  positions: AccountPosition[];
  sectors: { sector: string; weight_pct: number }[];
  risk: RiskMetrics | null;
  stress_tests: StressTest[];
}

export interface TransactionRow {
  id: number;
  ticker: string;
  side: "BUY" | "SELL";
  quantity: number;
  price: number;
  amount: number;
  session_date: string;
}

// ---------------------------------------------------------------- agents
export type Action = "BUY" | "HOLD" | "SELL" | "AVOID";

export interface Signal {
  name: "forecast" | "technical" | "sentiment" | "anomaly";
  available: boolean;
  score: number;
  reason?: string;
  expected_return_pct?: number;
  uncertainty_pct?: number;
  model?: string;
  rsi?: number | null;
  macd_histogram?: number | null;
  close_vs_sma50_pct?: number | null;
  articles?: number;
  severity?: MarketAlert["severity"] | null;
  count?: number;
  kinds?: string[];
  last_date?: string | null;
}

export interface Decision {
  action: Action;
  proposed_action: Action;
  score: number;
  threshold: number;
  coverage: number;
  contributions: { name: string; weight: number; score: number }[];
  illiquid: boolean;
  traded_share: number;
  safety_rules: { rule: string; triggered: boolean; effect: string | null }[];
  profile: RiskProfile;
  disclaimer: string;
  signals: Signal[];
  held_weight_pct: number | null;
  trust: Record<string, number> | null;
}

export interface AgentMessageRow {
  seq: number;
  sender: string;
  receiver: string;
  kind: "task" | "handoff" | "result" | "safety" | "error";
  summary: string;
  payload: Record<string, unknown>;
  at: string;
}

export interface RunSummary {
  id: number;
  ticker: string;
  risk_profile: RiskProfile;
  status: "running" | "done" | "failed";
  action: Action | null;
  score: number | null;
  started_at: string;
  finished_at: string | null;
}

export interface RunDetail extends RunSummary {
  result: Decision;
  messages: AgentMessageRow[];
  feedback?: { liked: boolean } | null;
}

export interface PolicyState {
  trust: Record<string, number>;
  updates: number;
  feedback: number;
  range: [number, number];
}

// ---------------------------------------------------------------- sentiment
export interface SentimentResult {
  score: number;
  label: "positive" | "negative" | "neutral";
  method: "llm" | "lexicon";
  language: "fr" | "ar" | "tunizi";
  reason: string | null;
  matches: { term: string; weight: number; negated: boolean }[];
  tickers: string[];
}

export interface Article {
  id: number;
  source: string;
  url: string;
  title: string;
  language: string;
  tickers: string[];
  score: number;
  label: SentimentResult["label"];
  method: string;
  published_at: string;
}
