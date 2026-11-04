"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/form";
import { Alert } from "@/components/ui/feedback";
import { api, errorMessage } from "@/lib/api";

export default function Contact() {
  const [state, setState] = useState<{ busy: boolean; ok?: string; err?: string }>({ busy: false });

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    setState({ busy: true });
    try {
      const r = await api<{ message: string }>("/contact", { body: { email: f.get("email"), subject: f.get("subject"), message: f.get("message") } });
      setState({ busy: false, ok: r.message });
      form.reset();
    } catch (err) {
      setState({ busy: false, err: errorMessage(err) });
    }
  }

  return (
    <div className="container max-w-xl py-14">
      <h1 className="text-3xl font-bold">Contact us</h1>
      <p className="mt-2 text-muted-foreground">Questions, feedback or privacy requests - we read everything.</p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        {state.ok && <Alert tone="success">{state.ok}</Alert>}
        {state.err && <Alert tone="error">{state.err}</Alert>}
        <Field label="Email" htmlFor="email"><Input id="email" name="email" type="email" required autoComplete="email" /></Field>
        <Field label="Subject" htmlFor="subject"><Input id="subject" name="subject" required minLength={3} maxLength={200} /></Field>
        <Field label="Message" htmlFor="message"><Textarea id="message" name="message" required minLength={10} maxLength={5000} rows={6} /></Field>
        <Button type="submit" loading={state.busy}>Send message</Button>
      </form>
    </div>
  );
}
