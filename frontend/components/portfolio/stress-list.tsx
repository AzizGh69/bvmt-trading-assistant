import { Change, Empty } from "@/components/states";
import type { StressTest } from "@/lib/api";
import { stressLabel } from "@/lib/profiles";
import { formatDate, sectorLabel } from "@/lib/utils";

export function StressList({ tests }: { tests: StressTest[] }) {
  if (!tests.length) return <Empty>Aucune position à éprouver.</Empty>;
  return (
    <ul className="divide-y divide-border">
      {tests.map((test) => (
        <li key={test.name} className="flex items-center justify-between gap-4 py-2.5">
          <div className="min-w-0">
            <p className="text-sm text-foreground">{stressLabel(test)}</p>
            <p className="text-[11px] text-muted">
              {test.kind === "historical" && test.from
                ? `${formatDate(test.from)}${test.to !== test.from ? ` – ${formatDate(test.to ?? test.from)}` : ""} · indice ${test.market_pct.toFixed(1)} %`
                : test.sector
                  ? `${sectorLabel(test.sector)}, ${test.sector_weight_pct?.toFixed(0)} % du portefeuille`
                  : "Toutes les valeurs baissent de 10 %"}
            </p>
          </div>
          <Change value={test.portfolio_pct} className="text-sm font-medium shrink-0" />
        </li>
      ))}
    </ul>
  );
}
