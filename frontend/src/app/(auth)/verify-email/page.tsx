"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Alert, Spinner } from "@/components/ui/feedback";
import { api, errorMessage } from "@/lib/api";

function Verify() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<"idle" | "working" | "ok" | "error">(token ? "working" : "idle");
  const [msg, setMsg] = useState("");
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (!token) return;
    api("/auth/verify-email", { body: { token } }).then(() => setState("ok")).catch((e) => { setMsg(errorMessage(e)); setState("error"); });
  }, [token]);

  async function resend(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const email = String(new FormData(e.currentTarget).get("email"));
    await api("/auth/resend-verification", { body: { email } }).catch(() => undefined);
    setSent(true);
  }

  if (state === "working") return <Spinner label="Verifying your email" />;
  if (state === "ok") return (<div className="space-y-3"><Alert tone="success" title="Email verified">Your account is ready.</Alert><Link className="text-primary hover:underline" href="/login">Continue to sign in</Link></div>);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Verify your email</h1>
      {state === "error" && <Alert tone="error">{msg}</Alert>}
      <p className="text-sm text-muted-foreground">Need a new verification link? Enter your email.</p>
      <form onSubmit={resend} className="space-y-3">
        <Field label="Email" htmlFor="email"><Input id="email" name="email" type="email" required /></Field>
        <Button type="submit" className="w-full">Send link</Button>
      </form>
      {sent && <Alert tone="success">If that address has an unverified account, a new link is on its way.</Alert>}
    </div>
  );
}

export default function VerifyEmailPage() { return <Suspense><Verify /></Suspense>; }
