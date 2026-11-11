"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { AlertTriangle, ArrowRight, Bot, ShieldCheck, ThumbsDown, ThumbsUp, XCircle } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Empty, ErrorNote, Loading } from "@/components/states";
import { api, type PolicyState, type RunDetail, type RunSummary, type StockSummary } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { useAuth } from "@/lib/auth-context";
import { ACTION_LABEL, ACTION_TONE, AGENT_LABEL, RULE_LABEL, describeMessage, describeSignal } from "@/lib/agents";
import { PROFILE_LABEL } from "@/lib/profiles";
import { cn, relativeTime } from "@/lib/utils";

const SIGNAL_LABEL: Record<string, string> = {
  forecast: "Prévision",
  technical: "Technique",
  sentiment: "Actualités",
  anomaly: "Anomalies",
};

export default function AgentsPage() {
  const { user } = useAuth();
  const stocks = useApi<StockSummary[]>("/api/stocks");
  const runs = useApi<RunSummary[]>(`/api/agents/runs?limit=15&u=${user?.id ?? 0}`);
  const [ticker, setTicker] = useState("");
  const [run, setRun] = useState<RunDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setRun(await api.post<RunDetail>("/api/agents/run", { ticker }));
      runs.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analyse impossible");
    } finally {
      setBusy(false);
    }
  }

  async function open(id: number) {
    setError(null);
    try {
      setRun(await api.get<RunDetail>(`/api/agents/runs/${id}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analyse introuvable");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Agents"
        description="Cinq agents analysent une valeur l’un après l’autre ; chaque passage de relais est enregistré."
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <form onSubmit={start} className="flex flex-col sm:flex-row gap-2">
            <Input list="agent-tickers" placeholder="Valeur à analyser (ex. SFBT)" required value={ticker} onChange={(e) => setTicker(e.target.value)} />
            <datalist id="agent-tickers">
              {(stocks.data ?? []).map((s) => (
                <option key={s.ticker} value={s.ticker}>
                  {s.name}
                </option>
              ))}
            </datalist>
            <Button type="submit" disabled={busy}>
              <Bot className="w-4 h-4" /> {busy ? "Analyse en cours…" : "Lancer les agents"}
            </Button>
          </form>
          <p className="mt-3 text-xs text-muted">
            Profil appliqué : {user ? PROFILE_LABEL[user.risk_profile] : "Équilibré (connectez-vous pour le vôtre)"}. Marché → Prévision →
            Sentiment → Anomalies → Recommandation.
          </p>
        </Card>
        <Card>
          <CardTitle>Analyses récentes</CardTitle>
          {runs.data && runs.data.length ? (
            <ul className="mt-3 divide-y divide-border">
              {runs.data.map((r) => (
                <li key={r.id}>
                  <button onClick={() => open(r.id)} className="w-full flex items-center justify-between py-2 text-sm hover:text-accent-light">
                    <span className="font-medium">{r.ticker}</span>
                    <span className="flex items-center gap-2">
                      {r.action && <Badge variant={ACTION_TONE[r.action]}>{ACTION_LABEL[r.action]}</Badge>}
                      <span className="text-[11px] text-muted">{relativeTime(r.started_at)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Aucune analyse pour l’instant.</Empty>
          )}
        </Card>
      </div>

      {error && <ErrorNote message={error} />}
      {busy && !run && <Loading label="Les agents travaillent…" />}
      {run && <RunView run={run} signedIn={!!user} onFeedback={() => open(run.id)} />}
    </div>
  );
}

function RunView({ run, signedIn, onFeedback }: { run: RunDetail; signedIn: boolean; onFeedback: () => void }) {
  const result = run.result;
  const triggered = result?.safety_rules?.filter((r) => r.triggered) ?? [];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <Card className="lg:col-span-3">
        <CardHeader>
          <CardTitle>
            Déroulé de l’analyse de{" "}
            <Link href={`/valeurs/${run.ticker}`} className="text-accent-light hover:underline">
              {run.ticker}
            </Link>
          </CardTitle>
          <span className="text-[11px] text-muted">#{run.id}</span>
        </CardHeader>
        <ol className="space-y-3">
          {run.messages.map((m) => (
            <li key={m.seq} className="flex gap-3">
              <div
                className={cn(
                  "mt-0.5 w-6 h-6 shrink-0 rounded-full flex items-center justify-center text-[11px] font-semibold",
                  m.kind === "error"
                    ? "bg-danger/15 text-danger"
                    : m.kind === "safety"
                      ? "bg-warning/15 text-warning"
                      : m.kind === "result"
                        ? "bg-success/15 text-success"
                        : "bg-accent/15 text-accent-light"
                )}
              >
                {m.kind === "error" ? <XCircle className="w-3.5 h-3.5" /> : m.kind === "safety" ? <ShieldCheck className="w-3.5 h-3.5" /> : m.seq}
              </div>
              <div className="min-w-0">
                <p className="text-xs text-muted flex items-center gap-1">
                  {AGENT_LABEL[m.sender] ?? m.sender} <ArrowRight className="w-3 h-3" /> {AGENT_LABEL[m.receiver] ?? m.receiver}
                  {typeof m.payload.elapsed_ms === "number" && <span className="ml-1">· {Math.round(m.payload.elapsed_ms as number)} ms</span>}
                </p>
                <p className="text-sm text-foreground">{describeMessage(m)}</p>
              </div>
            </li>
          ))}
        </ol>
      </Card>

      <div className="lg:col-span-2 space-y-6">
        {result?.action ? (
          <Card>
            <p className="text-[11px] uppercase tracking-wider text-muted">Recommandation, profil {PROFILE_LABEL[result.profile].toLowerCase()}</p>
            <div className="mt-2 flex items-center gap-3">
              <Badge variant={ACTION_TONE[result.action]} className="text-sm px-3 py-1">
                {ACTION_LABEL[result.action]}
              </Badge>
              {result.proposed_action !== result.action && (
                <span className="text-xs text-muted">les signaux disaient « {ACTION_LABEL[result.proposed_action]} »</span>
              )}
            </div>
            <p className="mt-3 text-xs text-muted">
              Score {result.score > 0 ? "+" : ""}
              {result.score.toFixed(2)} pour un seuil de ±{result.threshold} · {Math.round(result.coverage * 100)} % du poids des signaux
              disponible.
            </p>
            <ul className="mt-4 space-y-2.5">
              {result.signals.map((s) => (
                <li key={s.name} className={cn("text-sm", !s.available && "opacity-60")}>
                  <div className="flex justify-between">
                    <span className="font-medium">{SIGNAL_LABEL[s.name]}</span>
                    {s.name !== "anomaly" && <span className="tabular-nums">{s.available ? s.score.toFixed(2) : "absent"}</span>}
                  </div>
                  <p className="text-xs text-muted">{describeSignal(s)}</p>
                </li>
              ))}
            </ul>
            {triggered.length > 0 && (
              <div className="mt-4 space-y-1.5">
                {triggered.map((r) => (
                  <p key={r.rule} className="flex gap-2 text-xs text-warning">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {RULE_LABEL[r.rule] ?? r.rule}
                  </p>
                ))}
              </div>
            )}
            <p className="mt-4 text-[11px] text-muted">Calcul éducatif sur l’historique, pas un conseil en investissement.</p>
            {signedIn && <Feedback run={run} onDone={onFeedback} />}
          </Card>
        ) : (
          <ErrorNote message="Cette analyse n’a produit aucune recommandation." />
        )}
        {signedIn && <Trust key={`${run.id}-${run.feedback ? 1 : 0}`} />}
      </div>
    </div>
  );
}

function Feedback({ run, onDone }: { run: RunDetail; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  if (run.feedback)
    return <p className="mt-4 text-xs text-muted">Votre avis : {run.feedback.liked ? "utile" : "pas convaincant"}. Merci.</p>;
  async function send(liked: boolean) {
    try {
      await api.post(`/api/agents/runs/${run.id}/feedback`, { liked });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Avis refusé");
    }
  }
  return (
    <div className="mt-4 border-t border-border pt-3">
      <p className="text-xs text-muted mb-2">Cette recommandation vous semble-t-elle juste ? Votre avis ajuste le poids de chaque signal pour vous.</p>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => send(true)}>
          <ThumbsUp className="w-3.5 h-3.5" /> Oui
        </Button>
        <Button size="sm" variant="outline" onClick={() => send(false)}>
          <ThumbsDown className="w-3.5 h-3.5" /> Non
        </Button>
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}

function Trust() {
  const { data } = useApi<PolicyState>("/api/agents/policy");
  if (!data) return null;
  return (
    <Card>
      <CardTitle>Ce que vos avis ont appris</CardTitle>
      <p className="text-xs text-muted mt-1">
        {data.feedback} avis, dont {data.updates} sur un achat ou une vente (les « conserver » n’apprennent rien). Confiance entre{" "}
        {data.range[0]} et {data.range[1]} ; 1 = neutre.
      </p>
      <ul className="mt-3 space-y-2">
        {Object.entries(data.trust).map(([name, value]) => (
          <li key={name} className="text-sm">
            <div className="flex justify-between">
              <span className="text-muted">{SIGNAL_LABEL[name]}</span>
              <span className="tabular-nums">× {value.toFixed(2)}</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-card-hover overflow-hidden">
              <div className="h-full bg-accent" style={{ width: `${((value - data.range[0]) / (data.range[1] - data.range[0])) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
