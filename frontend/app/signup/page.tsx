"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { AuthFrame, Field } from "@/components/auth-frame";
import { ErrorNote } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type AuthResponse } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { PROFILE_LABEL, QUESTION_TEXT } from "@/lib/profiles";
import { cn } from "@/lib/utils";

export default function SignupPage() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [form, setForm] = useState({ username: "", email: "", password: "", capital: "10000" });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const complete = Object.keys(QUESTION_TEXT).every((q) => answers[q]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!complete) {
      setError("Répondez aux trois questions : elles fixent votre profil de risque.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await api.post<AuthResponse>("/api/auth/register", {
        username: form.username,
        email: form.email,
        password: form.password,
        initial_capital: Number(form.capital),
        answers,
      });
      signIn(response);
      router.push("/portefeuille");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Inscription impossible");
      setBusy(false);
    }
  }

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <AuthFrame
      title="Créer un compte"
      subtitle="Trois questions fixent votre profil de risque ; le portefeuille simulé démarre avec le capital choisi."
    >
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Nom affiché">
            <Input required minLength={2} maxLength={60} value={form.username} onChange={set("username")} />
          </Field>
          <Field label="Capital fictif (TND)">
            <Input type="number" required min={1000} max={10000000} step={500} value={form.capital} onChange={set("capital")} />
          </Field>
        </div>
        <Field label="Adresse e-mail">
          <Input type="email" autoComplete="email" required value={form.email} onChange={set("email")} />
        </Field>
        <Field label="Mot de passe (8 caractères au moins)">
          <Input
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            maxLength={72}
            value={form.password}
            onChange={set("password")}
          />
        </Field>

        {Object.entries(QUESTION_TEXT).map(([id, question]) => (
          <fieldset key={id} className="space-y-2">
            <legend className="text-xs font-medium text-foreground">{question.label}</legend>
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(question.choices).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setAnswers((a) => ({ ...a, [id]: value }))}
                  className={cn(
                    "rounded-md border px-2 py-2 text-xs transition-colors",
                    answers[id] === value
                      ? "border-accent bg-accent/10 text-foreground"
                      : "border-border text-muted hover:text-foreground hover:bg-card-hover"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </fieldset>
        ))}

        {complete && (
          <p className="text-xs text-muted">
            Profil obtenu : <span className="text-foreground font-medium">{PROFILE_LABEL[scoreProfile(answers)]}</span>.
            Vous pourrez le changer plus tard.
          </p>
        )}
        {error && <ErrorNote message={error} />}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Création…" : "Créer le compte"}
        </Button>
      </form>
      <p className="text-sm text-muted text-center">
        Déjà inscrit ?{" "}
        <Link href="/login" className="text-accent-light hover:underline">
          Se connecter
        </Link>
      </p>
    </AuthFrame>
  );
}

/** Mirrors profile_from_answers on the API, so the profile shows before submitting. */
function scoreProfile(answers: Record<string, string>) {
  const score = Object.entries(QUESTION_TEXT).reduce(
    (sum, [id, q]) => sum + Math.max(0, Object.keys(q.choices).indexOf(answers[id])),
    0
  );
  return score <= 2 ? "conservative" : score <= 4 ? "moderate" : "aggressive";
}
