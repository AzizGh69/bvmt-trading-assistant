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

export default function LoginPage() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      signIn(await api.post<AuthResponse>("/api/auth/login", { email, password }));
      router.push("/portefeuille");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connexion impossible");
      setBusy(false);
    }
  }

  return (
    <AuthFrame title="Se connecter" subtitle="Retrouvez votre portefeuille simulé et vos alertes.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Adresse e-mail">
          <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Mot de passe">
          <Input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {error && <ErrorNote message={error} />}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Connexion…" : "Se connecter"}
        </Button>
      </form>
      <p className="text-sm text-muted text-center">
        Pas encore de compte ?{" "}
        <Link href="/signup" className="text-accent-light hover:underline">
          Créer un compte
        </Link>
      </p>
    </AuthFrame>
  );
}
