"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, PageHeader, Spinner } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { api, errorMessage } from "@/lib/api";
import { cn, formatDate, formatMoney, titleCase } from "@/lib/utils";

function Sub() {
  const sp = useSearchParams();
  const [plans, setPlans] = useState<any>(null);
  const [me, setMe] = useState<any>(null);
  const [pays, setPays] = useState<any[]>([]);
  const [provider, setProvider] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, m, h] = await Promise.all([api("/billing/plans"), api("/billing/subscription"), api("/billing/payments")]);
      setPlans(p); setMe(m); setPays(h); setProvider((cur) => cur || p.providers[0] || "");
    } catch (e) { setErr(errorMessage(e)); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  // After returning from a provider checkout, plan changes arrive via a signed webhook - poll briefly for it.
  useEffect(() => {
    if (sp.get("checkout") !== "success") return;
    setInfo("Payment received by the provider. Waiting for confirmation…");
    let n = 0; const t = setInterval(async () => { n++; await load(); if (n > 10) clearInterval(t); }, 3000);
    return () => clearInterval(t);
  }, [sp, load]);

  async function choose(planKey: string) {
    setBusy(planKey); setErr(null);
    try {
      const r = await api("/billing/checkout", { body: { plan_key: planKey, provider } });
      if (provider === "sandbox") {
        const subId = new URL(r.checkout_url).searchParams.get("sandbox_sub")!;
        await api("/billing/sandbox/complete", { body: { subscription_id: subId } });
        setInfo("Sandbox payment completed (no real money)."); await load();
      } else window.location.href = r.checkout_url;
    } catch (e) { setErr(errorMessage(e)); } finally { setBusy(null); }
  }
  async function cancel() {
    if (!confirm("Cancel at the end of the current period?")) return;
    try { await api("/billing/cancel", { method: "POST" }); setInfo("Your plan stays active until the period ends."); await load(); } catch (e) { setErr(errorMessage(e)); }
  }

  if (!plans || !me) return err ? <Alert tone="error">{err}</Alert> : <Spinner />;
  const cur = me.plan.key;
  return (
    <>
      <PageHeader title="Subscription" description="Plans, usage and billing history." />
      {err && <Alert tone="error" className="mb-4">{err}</Alert>}
      {info && <Alert tone="success" className="mb-4">{info}</Alert>}
      {provider === "sandbox" && <Alert tone="warning" className="mb-4" title="Sandbox billing">Development mode: payments are simulated. No real money moves.</Alert>}
      <Card className="mb-6"><CardHeader><CardTitle>Current plan: {me.plan.name}</CardTitle></CardHeader><CardContent className="space-y-4">
        {me.subscription && <p className="text-sm text-muted-foreground">Status: <Badge tone={me.subscription.status === "active" ? "success" : "warning"}>{me.subscription.status}</Badge>{" "}renews/ends {formatDate(me.subscription.current_period_end)}{me.subscription.cancel_at_period_end ? " (cancelling)" : ""}</p>}
        {me.subscription?.status === "past_due" && <Alert tone="warning">Your last payment failed. Update your payment method to keep your plan.</Alert>}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{Object.entries(me.usage).map(([k, v]: any) => (
          <div key={k} className="rounded-md border p-3"><p className="text-xs text-muted-foreground">{titleCase(k.replace("_per_month", ""))}</p><p className="text-lg font-semibold">{v.used} <span className="text-sm font-normal text-muted-foreground">/ {v.limit}</span></p></div>))}</div>
        {me.subscription && !me.subscription.cancel_at_period_end && <Button variant="outline" onClick={cancel}>Cancel subscription</Button>}
      </CardContent></Card>

      {plans.providers.length > 0 ? <div className="mb-3 flex items-center gap-2"><label htmlFor="prov" className="text-sm">Pay with</label><Select id="prov" className="w-44" value={provider} onChange={(e) => setProvider(e.target.value)}>{plans.providers.map((p: string) => <option key={p} value={p}>{titleCase(p)}</option>)}</Select></div>
        : <Alert className="mb-3">No payment provider is configured on this server yet, so paid plans cannot be purchased.</Alert>}
      <div className="grid gap-4 md:grid-cols-3">{plans.plans.map((p: any) => (
        <Card key={p.key} className={cn(p.key === cur && "border-primary ring-1 ring-primary")}><CardHeader><CardTitle>{p.name}</CardTitle><p className="text-2xl font-bold">{p.price_inr ? formatMoney(p.price_inr) : "Free"}{p.price_inr > 0 && <span className="text-sm font-normal text-muted-foreground"> /mo</span>}</p></CardHeader>
          <CardContent className="space-y-3"><ul className="space-y-1.5 text-sm">{p.features.map((f: string) => <li key={f} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-success" />{f}</li>)}</ul>
            {p.key === cur ? <Badge tone="primary">Current plan</Badge> : p.key !== "free" && <Button className="w-full" disabled={!provider} loading={busy === p.key} onClick={() => choose(p.key)}>Choose {p.name}</Button>}</CardContent></Card>))}</div>

      <h2 className="mb-3 mt-8 text-lg font-semibold">Billing history</h2>
      {pays.length === 0 ? <p className="text-sm text-muted-foreground">No payments yet.</p> : (
        <div className="overflow-x-auto rounded-lg border"><table className="w-full text-left text-sm"><thead className="bg-muted text-xs uppercase text-muted-foreground"><tr><th className="p-3">Invoice</th><th className="p-3">Date</th><th className="p-3">Amount</th><th className="p-3">Status</th></tr></thead>
          <tbody className="divide-y">{pays.map((p) => <tr key={p.id}><td className="p-3 font-mono text-xs">{p.invoice_number ?? "-"}</td><td className="p-3">{formatDate(p.paid_at)}</td><td className="p-3">{formatMoney(p.amount, p.currency)}</td><td className="p-3"><Badge tone={p.status === "succeeded" ? "success" : p.status === "failed" ? "danger" : "default"}>{p.status}</Badge></td></tr>)}</tbody></table></div>)}
    </>
  );
}

export default function SubscriptionPage() { return <Suspense><Sub /></Suspense>; }
