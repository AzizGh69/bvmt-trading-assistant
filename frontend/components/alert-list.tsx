import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Change, Empty } from "@/components/states";
import type { MarketAlert } from "@/lib/api";
import { formatDate, formatNumber } from "@/lib/utils";

export const SEVERITY_LABEL: Record<MarketAlert["severity"], string> = {
  critical: "Critique",
  high: "Élevée",
  medium: "Moyenne",
  low: "Faible",
};

const SEVERITY_VARIANT: Record<MarketAlert["severity"], "danger" | "warning" | "info" | "muted"> = {
  critical: "danger",
  high: "warning",
  medium: "info",
  low: "muted",
};

/** What happened, in words, from the detectors that fired. */
export function describeAlert(alert: MarketAlert): string {
  const parts: string[] = [];
  if (alert.kinds.includes("corporate_action")) {
    parts.push("variation hors norme, probablement une opération sur titres (cours non ajustés)");
  }
  if (alert.kinds.includes("price_move")) parts.push("variation de cours de plus de 5 %");
  if (alert.kinds.includes("volume_spike") && alert.volume_z !== null) {
    parts.push(`volume à ${alert.volume_z.toFixed(1)} écarts-types au-dessus de sa moyenne sur 60 séances`);
  }
  if (alert.kinds.includes("pattern")) parts.push("combinaison inhabituelle de rendement, volume et amplitude");
  const text = parts.join(" ; ");
  return text.charAt(0).toUpperCase() + text.slice(1) + ".";
}

export function AlertList({ alerts, showTicker = true }: { alerts: MarketAlert[]; showTicker?: boolean }) {
  if (alerts.length === 0) return <Empty>Aucune séance signalée sur la période.</Empty>;
  return (
    <ul className="divide-y divide-border">
      {alerts.map((alert) => (
        <li key={`${alert.ticker}-${alert.date}`} className="flex items-start gap-4 py-3">
          <Badge variant={SEVERITY_VARIANT[alert.severity]} className="mt-0.5 w-[68px] justify-center shrink-0">
            {SEVERITY_LABEL[alert.severity]}
          </Badge>
          <div className="min-w-0 flex-1">
            <p className="text-sm">
              {showTicker && (
                <Link href={`/valeurs/${encodeURIComponent(alert.ticker)}`} className="font-medium hover:underline">
                  {alert.ticker}
                </Link>
              )}
              <span className={showTicker ? "text-muted" : "font-medium"}>
                {showTicker ? " · " : ""}
                {formatDate(alert.date)}
              </span>
            </p>
            <p className="text-xs text-muted mt-0.5">{describeAlert(alert)}</p>
          </div>
          <div className="text-right shrink-0 text-xs">
            <Change value={alert.change_pct} className="block text-sm" />
            <span className="text-muted tabular-nums">{formatNumber(alert.volume)} titres</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
