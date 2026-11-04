"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/feedback";
import { api, errorMessage } from "@/lib/api";

function Reset() {
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<{ busy?: boolean; ok?: boolean; err?: string }>({});
  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (f.get("password") !== f.get("confirm")) { setState({ err: "Passwords do not match." }); return; }
    setState({ busy: true });
    try { await api("/auth/reset-password", { body: { token, new_password: f.get("password") } }); setState({ ok: true }); }
    catch (err) { setState({ err: errorMessage(err) }); }
  }
  if (state.ok) return <div className="space-y-3"><Alert tone="success" title="Password updated">All other sessions were signed out.</Alert><Link className="text-primary hover:underline" href="/login">Sign in</Link></div>;
  return (
    <>
      <h1 className="text-2xl font-semibold">Choose a new password</h1>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        {!token && <Alert tone="error">This reset link is missing its token. Request a new one.</Alert>}
        {state.err && <Alert tone="error">{state.err}</Alert>}
        <Field label="New password" htmlFor="password" hint="At least 10 characters with letters and numbers."><Input id="password" name="password" type="password" minLength={10} required autoComplete="new-password" /></Field>
        <Field label="Confirm password" htmlFor="confirm"><Input id="confirm" name="confirm" type="password" required autoComplete="new-password" /></Field>
        <Button type="submit" className="w-full" loading={state.busy} disabled={!token}>Update password</Button>
      </form>
    </>
  );
}

export default function ResetPasswordPage() { return <Suspense><Reset /></Suspense>; }
