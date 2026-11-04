"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, PageHeader, Spinner } from "@/components/ui/feedback";
import { Checkbox, Field, Input } from "@/components/ui/form";
import { adminApi, errorMessage } from "@/lib/api";
import { titleCase } from "@/lib/utils";

export default function AdminPlans() {
  const [plans, setPlans] = useState<any[] | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  useEffect(() => { adminApi("/plans").then(setPlans).catch((e) => setMsg({ tone: "error", text: errorMessage(e) })); }, []);
  const edit = (key: string, patch: any) => setPlans((ps) => ps!.map((p) => (p.key === key ? { ...p, ...patch } : p)));
  async function save(p: any) {
    try { await adminApi(`/plans/${p.key}`, { method: "PATCH", body: { limits: p.limits, price_inr: p.price_inr, is_active: p.is_active, razorpay_plan_id: p.razorpay_plan_id, stripe_price_id: p.stripe_price_id } }); setMsg({ tone: "success", text: `${p.name} saved.` }); }
    catch (e) { setMsg({ tone: "error", text: errorMessage(e) }); }
  }
  if (!plans) return <Spinner />;
  return (
    <>
      <PageHeader title="Plans and limits" description="Every limit is a number - there is deliberately no 'unlimited'." />
      {msg && <Alert tone={msg.tone} className="mb-4">{msg.text}</Alert>}
      <div className="grid gap-4 xl:grid-cols-3">{plans.map((p) => (
        <Card key={p.key}><CardHeader><CardTitle>{p.name}</CardTitle></CardHeader><CardContent className="space-y-3">
          <Field label="Price (paise)" htmlFor={`pr-${p.key}`}><Input id={`pr-${p.key}`} type="number" min={0} value={p.price_inr} onChange={(e) => edit(p.key, { price_inr: Number(e.target.value) })} /></Field>
          {Object.entries(p.limits).map(([k, v]: any) => typeof v === "boolean"
            ? <Checkbox key={k} label={titleCase(k)} checked={v} onChange={(e) => edit(p.key, { limits: { ...p.limits, [k]: e.target.checked } })} />
            : <Field key={k} label={titleCase(k)} htmlFor={`${p.key}-${k}`}><Input id={`${p.key}-${k}`} type="number" min={0} value={v} onChange={(e) => edit(p.key, { limits: { ...p.limits, [k]: Number(e.target.value) } })} /></Field>)}
          {p.key !== "free" && <><Field label="Razorpay plan id" htmlFor={`rz-${p.key}`}><Input id={`rz-${p.key}`} value={p.razorpay_plan_id ?? ""} onChange={(e) => edit(p.key, { razorpay_plan_id: e.target.value })} /></Field>
            <Field label="Stripe price id" htmlFor={`st-${p.key}`}><Input id={`st-${p.key}`} value={p.stripe_price_id ?? ""} onChange={(e) => edit(p.key, { stripe_price_id: e.target.value })} /></Field></>}
          <Checkbox label="Plan is active" checked={p.is_active} onChange={(e) => edit(p.key, { is_active: e.target.checked })} />
          <Button onClick={() => save(p)}>Save {p.name}</Button></CardContent></Card>))}</div>
    </>
  );
}
