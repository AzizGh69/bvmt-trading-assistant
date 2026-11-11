import type { Action, AgentMessageRow, Signal } from "@/lib/api";

export const AGENT_LABEL: Record<string, string> = {
  orchestrator: "Orchestrateur",
  market: "Marché",
  forecast: "Prévision",
  sentiment: "Sentiment",
  anomaly: "Anomalies",
  recommendation: "Recommandation",
};

export const ACTION_LABEL: Record<Action, string> = {
  BUY: "Acheter",
  HOLD: "Conserver / attendre",
  SELL: "Vendre",
  AVOID: "Éviter",
};

export const ACTION_TONE: Record<Action, "success" | "muted" | "danger" | "warning"> = {
  BUY: "success",
  HOLD: "muted",
  SELL: "danger",
  AVOID: "warning",
};

export const RULE_LABEL: Record<string, string> = {
  not_listed: "La valeur n’est plus cotée : pas d’achat.",
  recent_anomaly: "Séance inhabituelle (élevée ou critique) dans les 5 dernières : on attend avant d’acheter.",
  illiquid: "Valeur peu liquide (cotée moins d’une séance sur deux) : pas d’achat pour un profil prudent ou équilibré.",
  thin_evidence: "Moins de la moitié des signaux disponibles : pas de décision.",
  position_cap: "La ligne dépasse déjà le plafond de votre profil : pas de renforcement.",
  no_short_selling: "Vous ne détenez pas la valeur et la vente à découvert n’existe pas ici : « éviter ».",
};

const SEVERITY: Record<string, string> = { low: "faible", medium: "moyenne", high: "élevée", critical: "critique" };
const MODEL: Record<string, string> = { arima: "ARIMA", ema: "moyenne exponentielle", naive: "marche aléatoire" };
const pct = (v: unknown, digits = 2) => (typeof v === "number" ? `${v > 0 ? "+" : ""}${v.toFixed(digits)} %` : "–");

/** One hand-off, said in French from its payload (the API logs English). */
export function describeMessage(m: AgentMessageRow): string {
  const p = m.payload as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  if (m.kind === "error") return `Échec de l’agent : ${p.error ?? m.summary}. Son signal est écarté.`;
  if (m.kind === "task") return `Analyser ${p.ticker}.`;
  if (m.kind === "safety") return RULE_LABEL[p.rule] ?? m.summary;
  switch (m.sender) {
    case "market":
      return `Clôture ${p.close} TND le ${p.session} ; cotée ${Math.round(p.traded_share_60 * 100)} % des 60 dernières séances.${
        p.news_refresh === "disabled" ? "" : " Flux d’actualités relus."
      }`;
    case "forecast":
      if (!p.available) return "Historique trop court : pas de prévision.";
      return `${MODEL[p.model.selected] ?? p.model.selected} : ${pct(p.expected_return_pct)} sur 5 séances, ${
        p.model.beats_random_walk ? "meilleur que la marche aléatoire au backtest" : "pas meilleur que la marche aléatoire : signal ignoré"
      }.`;
    case "sentiment":
      return p.articles
        ? `${p.articles} article${p.articles > 1 ? "s" : ""} en 30 jours, sentiment moyen ${p.score > 0 ? "+" : ""}${p.score.toFixed(2)}.`
        : `Aucun article sur 30 jours${p.scraping_enabled ? "" : " (lecture des actualités désactivée)"}.`;
    case "anomaly":
      return p.alert.severity
        ? `${p.alert.count} séance(s) inhabituelle(s) sur 5, la pire de gravité ${SEVERITY[p.alert.severity]}.`
        : "Aucune séance inhabituelle sur les 5 dernières.";
    case "recommendation":
      return `${ACTION_LABEL[p.action as Action]} : score ${p.score > 0 ? "+" : ""}${p.score.toFixed(2)} pour un seuil de ±${p.threshold}.`;
  }
  return m.summary;
}

export function describeSignal(s: Signal): string {
  switch (s.name) {
    case "forecast":
      return s.reason === "model_no_better_than_random_walk"
        ? "Modèle pas meilleur que la marche aléatoire : ignoré."
        : s.available
          ? `${pct(s.expected_return_pct)} attendus, incertitude ±${s.uncertainty_pct?.toFixed(2)} %.`
          : "Pas de prévision.";
    case "technical":
      return s.available
        ? `RSI ${s.rsi?.toFixed(0) ?? "–"}, cours ${pct(s.close_vs_sma50_pct, 1)} par rapport à la moyenne 50 séances, MACD ${
            (s.macd_histogram ?? 0) >= 0 ? "au-dessus" : "au-dessous"
          } de son signal.`
        : "Historique insuffisant.";
    case "sentiment":
      return s.available ? `${s.articles} article(s) récents.` : "Aucune actualité récente : absent.";
    case "anomaly":
      return s.available ? `Gravité ${SEVERITY[s.severity ?? "low"]} : un avertissement, pas une direction.` : "Rien d’inhabituel.";
  }
}
