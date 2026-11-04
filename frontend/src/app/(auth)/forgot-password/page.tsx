"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/feedback";
import { api, errorMessage } from "@/lib/api";

export default function ForgotPassword() {
  const [state, setState] = useState<{ busy?: boolean; sent?: boolean; err?: string }>({});
  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setState({ busy: true });
    try { await api("/auth/forgot-password", { body: { email: String(new FormData(e.currentTarget).get("email")).trim() } }); setState({ sent: true }); }
    catch (err) { setState({ err: errorMessage(err) }); }
  }
  return (
    <>
      <h1 className="text-2xl font-semibold">Reset your password</h1>
      {state.sent ? <div className="mt-4"><Alert tone="success">If an account exists for that email, we have sent a reset link.</Alert></div> : (
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          {state.err && <Alert tone="error">{state.err}</Alert>}
          <Field label="Email" htmlFor="email"><Input id="email" name="email" type="email" required autoComplete="email" /></Field>
          <Button type="submit" className="w-full" loading={state.busy}>Send reset link</Button>
        </form>
      )}
      <p className="mt-6 text-sm"><Link className="text-primary hover:underline" href="/login">Back to sign in</Link></p>
    </>
  );
}
