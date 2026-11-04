"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/feedback";
import { api, errorMessage } from "@/lib/api";

export default function RegisterPage() {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (f.get("password") !== f.get("confirm")) { setErr("Passwords do not match."); return; }
    setBusy(true); setErr(null);
    try {
      const email = String(f.get("email")).trim();
      await api("/auth/register", { body: { email, password: f.get("password"), full_name: String(f.get("name") || "").trim() || null, accept_terms: f.get("terms") === "on", accept_privacy: f.get("privacy") === "on" } });
      setDone(email);
    } catch (e2) { setErr(errorMessage(e2)); } finally { setBusy(false); }
  }

  if (done) return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold">Check your email</h1>
      <p className="text-sm text-muted-foreground">If <strong>{done}</strong> can be registered, we have sent a verification link. It expires soon - open it to activate your account.</p>
      <Link className="text-sm text-primary hover:underline" href="/login">Back to sign in</Link>
    </div>
  );

  return (
    <>
      <h1 className="text-2xl font-semibold">Create your account</h1>
      <p className="mt-1 text-sm text-muted-foreground">Free plan - no card needed.</p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        {err && <Alert tone="error">{err}</Alert>}
        <Field label="Full name" htmlFor="name"><Input id="name" name="name" autoComplete="name" /></Field>
        <Field label="Email" htmlFor="email"><Input id="email" name="email" type="email" autoComplete="email" required /></Field>
        <Field label="Password" htmlFor="password" hint="At least 10 characters with letters and numbers."><Input id="password" name="password" type="password" autoComplete="new-password" required minLength={10} /></Field>
        <Field label="Confirm password" htmlFor="confirm"><Input id="confirm" name="confirm" type="password" autoComplete="new-password" required /></Field>
        <Checkbox name="terms" required label={<>I accept the <Link className="text-primary underline" href="/terms" target="_blank">Terms of Service</Link></>} />
        <Checkbox name="privacy" required label={<>I accept the <Link className="text-primary underline" href="/privacy" target="_blank">Privacy Policy</Link></>} />
        <Button type="submit" className="w-full" loading={busy}>Create account</Button>
      </form>
      <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground"><span className="h-px flex-1 bg-border" />or<span className="h-px flex-1 bg-border" /></div>
      <a href="/api/auth/google/login" className="inline-flex h-10 w-full items-center justify-center rounded-md border text-sm font-medium hover:bg-accent">Continue with Google</a>
      <p className="mt-6 text-sm">Already registered? <Link className="text-primary hover:underline" href="/login">Sign in</Link></p>
    </>
  );
}
