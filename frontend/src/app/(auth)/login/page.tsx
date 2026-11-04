"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/feedback";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { refresh } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(params.get("error") ? "Sign-in did not complete. Please try again." : null);
  const [unverified, setUnverified] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true); setErr(null);
    try {
      await api("/auth/login", { body: { email: String(f.get("email")).trim(), password: f.get("password") } });
      const u = await refresh();
      const next = params.get("next");
      router.push(u && !u.onboarding_completed ? "/onboarding" : next && next.startsWith("/") ? next : "/dashboard");
    } catch (e2) {
      setUnverified(e2 instanceof ApiError && e2.code === "email_not_verified");
      setErr(errorMessage(e2));
    } finally { setBusy(false); }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">Welcome back</h1>
      <p className="mt-1 text-sm text-muted-foreground">Sign in to your account.</p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        {err && <Alert tone="error">{err}</Alert>}
        {unverified && <p className="text-sm">Check your inbox for the verification link, or <Link className="text-primary underline" href="/verify-email">resend it</Link>.</p>}
        <Field label="Email" htmlFor="email"><Input id="email" name="email" type="email" autoComplete="email" required /></Field>
        <Field label="Password" htmlFor="password"><Input id="password" name="password" type="password" autoComplete="current-password" required /></Field>
        <Button type="submit" className="w-full" loading={busy}>Sign in</Button>
      </form>
      <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground"><span className="h-px flex-1 bg-border" />or<span className="h-px flex-1 bg-border" /></div>
      <a href="/api/auth/google/login" className="inline-flex h-10 w-full items-center justify-center rounded-md border text-sm font-medium hover:bg-accent">Continue with Google</a>
      <p className="mt-6 flex justify-between text-sm"><Link className="text-primary hover:underline" href="/forgot-password">Forgot password?</Link><Link className="text-primary hover:underline" href="/register">Create account</Link></p>
    </>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
