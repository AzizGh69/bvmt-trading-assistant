"use client";

import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ErrorNote, Loading } from "@/components/states";
import { RecommendationView } from "@/components/portfolio/recommendation-view";
import { PaperAccount } from "@/components/portfolio/paper-account";
import { api, type Recommendation, type RiskProfile } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useApi } from "@/lib/use-api";
import { PROFILE_HINT, PROFILE_LABEL } from "@/lib/profiles";
import { formatDate } from "@/lib/utils";

const VIEWS = [
  { id: "plan", label: "Allocation recommandée" },
  { id: "account", label: "Mon portefeuille simulé" },
];

export default function PortfolioPage() {
  const { user, loading, refresh } = useAuth();
  const [view, setView] = useState("plan");
  const [chosen, setChosen] = useState<RiskProfile | null>(null);
  const profile = chosen ?? user?.risk_profile ?? "moderate";

  async function changeProfile(next: RiskProfile) {
    await api.put("/api/auth/profile", { risk_profile: next });
    await refresh();
    setChosen(null);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Portefeuille"
        description="Allocation Markowitz par profil de risque, et un compte fictif pour la mettre à l’épreuve."
      >
        <Tabs tabs={VIEWS} defaultTab={view} onChange={setView} />
      </PageHeader>

      {view === "plan" ? (
        <>
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <Tabs
              key={profile}
              tabs={(Object.keys(PROFILE_LABEL) as RiskProfile[]).map((p) => ({ id: p, label: PROFILE_LABEL[p] }))}
              defaultTab={profile}
              onChange={(p) => setChosen(p as RiskProfile)}
            />
            <p className="text-xs text-muted">
              {PROFILE_HINT[profile]}
              {user && profile === user.risk_profile ? " C’est votre profil." : ""}
            </p>
          </div>
          <Plan profile={profile} />
        </>
      ) : loading ? (
        <Loading />
      ) : user ? (
        <PaperAccount user={user} onProfileChange={changeProfile} />
      ) : (
        <Card className="text-center py-10 space-y-4">
          <p className="text-sm text-muted max-w-md mx-auto">
            Le portefeuille simulé garde vos positions d’une visite à l’autre : il demande un compte. L’allocation recommandée
            reste consultable sans compte.
          </p>
          <div className="flex justify-center gap-2">
            <Link href="/signup">
              <Button>Créer un compte</Button>
            </Link>
            <Link href="/login">
              <Button variant="outline">Se connecter</Button>
            </Link>
          </div>
        </Card>
      )}
    </div>
  );
}

function Plan({ profile }: { profile: RiskProfile }) {
  const { data, error, loading } = useApi<Recommendation>(`/api/portfolio/recommendation?profile=${profile}&capital=10000`);
  if (error) return <ErrorNote message={error} />;
  if (!data) return <Loading label="Optimisation du portefeuille…" />;
  return (
    <div className={loading ? "opacity-60 transition-opacity" : undefined}>
      <p className="text-xs text-muted mb-4">
        Calculé sur la séance du {formatDate(data.session)} ; titres et montants pour 10 000 TND.
      </p>
      <RecommendationView plan={data} />
    </div>
  );
}
