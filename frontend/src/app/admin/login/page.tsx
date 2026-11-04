"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/form";
import { adminApi, errorMessage } from "@/lib/api";

export default function AdminLogin() {
  const router = useRouter();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget); setBusy(true); setErr(null);
    try { await adminApi("/login", { body: { email: f.get("email"), password: f.get("password") } }); router.push("/admin"); } catch (er) { setErr(errorMessage(er)); } finally { setBusy(false); }
  }
  return (
    <main id="main" className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-xl border bg-card p-6 shadow-sm">
        <h1 className="text-xl font-semibold">Admin sign in</h1>
        {err && <Alert tone="error">{err}</Alert>}
        <Field label="Email" htmlFor="email"><Input id="email" name="email" type="email" required autoComplete="username" /></Field>
        <Field label="Password" htmlFor="password"><Input id="password" name="password" type="password" required autoComplete="current-password" /></Field>
        <Button type="submit" className="w-full" loading={busy}>Sign in</Button>
      </form>
    </main>
  );
}
