import type { RiskProfile, StressTest } from "@/lib/api";

export const PROFILE_LABEL: Record<RiskProfile, string> = {
  conservative: "Prudent",
  moderate: "Équilibré",
  aggressive: "Dynamique",
};

export const PROFILE_HINT: Record<RiskProfile, string> = {
  conservative: "Volatilité faible, 15 % au plus par valeur.",
  moderate: "Compromis rendement / risque, 25 % au plus par valeur.",
  aggressive: "Accepte plus de volatilité, 35 % au plus par valeur.",
};

/** The sign-up questionnaire, in the order the API scores it. */
export const QUESTION_TEXT: Record<string, { label: string; choices: Record<string, string> }> = {
  horizon: {
    label: "Pendant combien de temps comptez-vous investir ?",
    choices: { short: "Moins d’un an", medium: "De 1 à 5 ans", long: "Plus de 5 ans" },
  },
  loss_reaction: {
    label: "Votre portefeuille perd 10 % en un mois. Que faites-vous ?",
    choices: { sell: "Je vends pour limiter la perte", hold: "J’attends", buy_more: "J’en rachète" },
  },
  experience: {
    label: "Avez-vous déjà investi en bourse ?",
    choices: { none: "Jamais", some: "Un peu", experienced: "Régulièrement" },
  },
};

export const REASON_LABEL = {
  diversifier: "Diversifie",
  return_driver: "Porte le rendement",
  core: "Socle",
} as const;

export function stressLabel(test: StressTest): string {
  switch (test.name) {
    case "worst_20_sessions":
      return "Pires 20 séances de l’indice";
    case "worst_session":
      return "Pire séance de l’indice";
    case "market_minus_10":
      return "Marché −10 %";
    case "largest_sector_minus_15":
      return "Premier secteur −15 %";
  }
}
