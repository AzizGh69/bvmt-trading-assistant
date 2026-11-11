"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { RotateCcw, Wand2 } from "lucide-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Change, Empty, ErrorNote, Loading } from "@/components/states";
import { StressList } from "@/components/portfolio/stress-list";
import { api, type Account, type RiskProfile, type StockSummary, type TransactionRow, type User } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { PROFILE_LABEL } from "@/lib/profiles";
import { cn, formatCurrency, formatDate, sectorLabel } from "@/lib/utils";

export function PaperAccount({ user, onProfileChange }: { user: User; onProfileChange: (p: RiskProfile) => Promise<void> }) {
  const account = useApi<Account>("/api/portfolio");
  const transactions = useApi<TransactionRow[]>("/api/portfolio/transactions?limit=50");
  const stocks = useApi<StockSummary[]>("/api/stocks");
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = () => {
    account.reload();
    transactions.reload();
  };

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setMessage(null);
    try {
      setMessage({ tone: "ok", text: await action() });
      reload();
    } catch (e) {
      setMessage({ tone: "error", text: e instanceof Error ? e.message : "Opération refusée" });
    } finally {
      setBusy(false);
    }
  }

  if (account.error && !account.data) return <ErrorNote message={account.error} />;
  if (!account.data) return <Loading label="Chargement du compte…" />;
  const acct = account.data;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Figure label="Valeur totale" value={formatCurrency(acct.total_value)}>
          <Change value={acct.pnl_pct} className="text-xs" /> depuis {formatCurrency(acct.initial_capital)}
        </Figure>
        <Figure label="Liquidités" value={formatCurrency(acct.cash)}>
          {acct.total_value > 0 ? `${((acct.cash / acct.total_value) * 100).toFixed(1)} % du compte` : ""}
        </Figure>
        <Figure label="Investi" value={formatCurrency(acct.invested)}>
          {acct.positions.length} ligne{acct.positions.length > 1 ? "s" : ""}
        </Figure>
        <Figure label="VaR 95 % (1 séance)" value={acct.risk?.var95_tnd ? formatCurrency(acct.risk.var95_tnd) : "–"}>
          perte dépassée une séance sur vingt
        </Figure>
      </div>

      <Card>
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <CardTitle>Profil de risque : {PROFILE_LABEL[user.risk_profile]}</CardTitle>
            <p className="text-xs text-muted mt-1">
              Cours de la séance du {formatDate(acct.session)}. Les ordres s’exécutent au dernier cours de clôture, sans frais ni
              carnet d’ordres.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {(Object.keys(PROFILE_LABEL) as RiskProfile[]).map((p) => (
              <Button
                key={p}
                size="sm"
                variant={p === user.risk_profile ? "default" : "outline"}
                disabled={busy || p === user.risk_profile}
                onClick={() => run(async () => (await onProfileChange(p), `Profil changé : ${PROFILE_LABEL[p]}.`))}
              >
                {PROFILE_LABEL[p]}
              </Button>
            ))}
            <Button
              size="sm"
              variant="success"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const r = await api.post<{ orders: number }>("/api/portfolio/apply-recommendation");
                  return r.orders ? `${r.orders} ordre${r.orders > 1 ? "s" : ""} passé${r.orders > 1 ? "s" : ""} pour suivre l’allocation.` : "Le compte suit déjà l’allocation.";
                })
              }
            >
              <Wand2 className="w-3.5 h-3.5" /> Suivre l’allocation recommandée
            </Button>
          </div>
        </div>
        {message && (
          <p className={cn("mt-3 text-sm", message.tone === "ok" ? "text-success" : "text-danger")}>{message.text}</p>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card padding={false} className="lg:col-span-2">
          <div className="p-5 pb-3">
            <CardTitle>Positions</CardTitle>
          </div>
          {acct.positions.length === 0 ? (
            <Empty>Aucune position. Passez un ordre ou suivez l’allocation recommandée.</Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] uppercase tracking-wider text-muted border-y border-border">
                    <th className="text-left font-medium px-5 py-2">Valeur</th>
                    <th className="text-right font-medium px-3 py-2">Quantité</th>
                    <th className="text-right font-medium px-3 py-2">PRU</th>
                    <th className="text-right font-medium px-3 py-2">Cours</th>
                    <th className="text-right font-medium px-3 py-2">Montant</th>
                    <th className="text-right font-medium px-5 py-2">+/− value</th>
                  </tr>
                </thead>
                <tbody>
                  {acct.positions.map((p) => (
                    <tr key={p.ticker} className="border-b border-border last:border-0 hover:bg-card-hover">
                      <td className="px-5 py-2.5">
                        <Link href={`/valeurs/${p.ticker}`} className="font-medium hover:text-accent-light">
                          {p.ticker}
                        </Link>
                        <span className="block text-[11px] text-muted">{p.weight_pct.toFixed(1)} % du compte</span>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{p.quantity}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{p.avg_cost.toFixed(3)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{p.last_close.toFixed(3)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatCurrency(p.market_value)}</td>
                      <td className="px-5 py-2.5 text-right">
                        <Change value={p.pnl_pct} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <OrderForm stocks={stocks.data ?? []} busy={busy} run={run} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Risque des positions actuelles</CardTitle>
          </CardHeader>
          {acct.risk ? (
            <dl className="space-y-2 text-sm">
              {(
                [
                  ["Volatilité annualisée", acct.risk.volatility_pct, "%"],
                  ["Perte maximale", acct.risk.max_drawdown_pct, "%"],
                  ["VaR 95 %", acct.risk.var95_pct, "%"],
                  ["CVaR 95 %", acct.risk.cvar95_pct, "%"],
                  ["Ratio de Sharpe", acct.risk.sharpe, ""],
                ] as const
              ).map(([label, value, unit]) => (
                <div key={label} className="flex justify-between">
                  <dt className="text-muted">{label}</dt>
                  <dd className="tabular-nums">{value === null ? "–" : `${value.toFixed(2)}${unit ? ` ${unit}` : ""}`}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <Empty>Pas de position, pas de risque.</Empty>
          )}
          <p className="mt-3 text-[11px] text-muted">
            Les poids d’aujourd’hui rejoués sur les 250 dernières séances. Si ces poids viennent de l’optimiseur, ces séances ont servi à
            les choisir : chiffres flatteurs, voir le test hors échantillon.
          </p>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Résistance aux chocs</CardTitle>
          </CardHeader>
          <StressList tests={acct.stress_tests} />
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Secteurs</CardTitle>
          </CardHeader>
          {acct.sectors.length ? (
            <ul className="space-y-2">
              {acct.sectors.map((s) => (
                <li key={s.sector} className="text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted">{sectorLabel(s.sector)}</span>
                    <span className="tabular-nums">{s.weight_pct.toFixed(1)} %</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-card-hover overflow-hidden">
                    <div className="h-full bg-accent" style={{ width: `${Math.min(100, s.weight_pct)}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Rien d’investi.</Empty>
          )}
        </Card>
      </div>

      <Card padding={false}>
        <div className="p-5 pb-3 flex items-center justify-between">
          <CardTitle>Historique des ordres</CardTitle>
          <ResetButton busy={busy} capital={acct.initial_capital} run={run} />
        </div>
        {transactions.data && transactions.data.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <tbody>
                {transactions.data.map((t) => (
                  <tr key={t.id} className="border-t border-border">
                    <td className="px-5 py-2 text-muted">{formatDate(t.session_date)}</td>
                    <td className="px-3 py-2">
                      <Badge variant={t.side === "BUY" ? "success" : "danger"}>{t.side === "BUY" ? "Achat" : "Vente"}</Badge>
                    </td>
                    <td className="px-3 py-2 font-medium">{t.ticker}</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {t.quantity} × {t.price.toFixed(3)}
                    </td>
                    <td className="px-5 py-2 text-right tabular-nums">{formatCurrency(t.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>Aucun ordre pour l’instant.</Empty>
        )}
      </Card>
    </div>
  );
}

function Figure({ label, value, children }: { label: string; value: string; children: React.ReactNode }) {
  return (
    <Card>
      <p className="text-[11px] uppercase tracking-wider text-muted">{label}</p>
      <p className="mt-2 text-xl font-bold tabular-nums text-foreground">{value}</p>
      <p className="text-[11px] text-muted mt-0.5">{children}</p>
    </Card>
  );
}

function OrderForm({
  stocks,
  busy,
  run,
}: {
  stocks: StockSummary[];
  busy: boolean;
  run: (action: () => Promise<string>) => Promise<void>;
}) {
  const [ticker, setTicker] = useState("");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [quantity, setQuantity] = useState("10");
  const match = stocks.find((s) => s.ticker === ticker.trim().toUpperCase());
  const estimate = match ? match.last_close * Number(quantity || 0) : null;

  function submit(event: FormEvent) {
    event.preventDefault();
    run(async () => {
      const r = await api.post<{ order: { ticker: string; quantity: number; price: number } }>("/api/portfolio/orders", {
        ticker,
        side,
        quantity: Number(quantity),
      });
      return `${side === "BUY" ? "Achat" : "Vente"} de ${r.order.quantity} ${r.order.ticker} à ${r.order.price.toFixed(3)} TND.`;
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Passer un ordre</CardTitle>
      </CardHeader>
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          {(["BUY", "SELL"] as const).map((s) => (
            <Button key={s} type="button" size="sm" variant={side === s ? (s === "BUY" ? "success" : "danger") : "outline"} onClick={() => setSide(s)}>
              {s === "BUY" ? "Acheter" : "Vendre"}
            </Button>
          ))}
        </div>
        <Input list="tickers" placeholder="Valeur (ex. SFBT)" required value={ticker} onChange={(e) => setTicker(e.target.value)} />
        <datalist id="tickers">
          {stocks.map((s) => (
            <option key={s.ticker} value={s.ticker}>
              {s.name}
            </option>
          ))}
        </datalist>
        <Input type="number" min={1} step={1} required value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        <p className="text-xs text-muted min-h-4">
          {match ? `${match.name} · ${match.last_close.toFixed(3)} TND · ≈ ${formatCurrency(estimate ?? 0)}` : ""}
        </p>
        <Button type="submit" className="w-full" disabled={busy}>
          Valider l’ordre
        </Button>
      </form>
    </Card>
  );
}

function ResetButton({ busy, capital, run }: { busy: boolean; capital: number; run: (a: () => Promise<string>) => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  if (!confirming)
    return (
      <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirming(true)}>
        <RotateCcw className="w-3.5 h-3.5" /> Repartir de zéro
      </Button>
    );
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted">Tout vendre et effacer l’historique ?</span>
      <Button
        size="sm"
        variant="danger"
        disabled={busy}
        onClick={() =>
          run(async () => {
            setConfirming(false);
            await api.post("/api/portfolio/reset", { initial_capital: capital });
            return `Compte remis à ${formatCurrency(capital)}.`;
          })
        }
      >
        Confirmer
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
        Annuler
      </Button>
    </div>
  );
}
