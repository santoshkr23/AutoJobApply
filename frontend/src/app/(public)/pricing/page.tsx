"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/feedback";
import { api } from "@/lib/api";
import { cn, formatMoney } from "@/lib/utils";

type Plan = { key: string; name: string; description: string; price_inr: number; features: string[] };

export default function Pricing() {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { api<{ plans: Plan[] }>("/billing/plans").then((d) => setPlans(d.plans)).catch(() => setErr(true)); }, []);

  return (
    <div className="container py-14">
      <div className="mx-auto max-w-2xl text-center">
        <h1 className="text-3xl font-bold">Simple pricing</h1>
        <p className="mt-2 text-muted-foreground">Every limit is stated. No "unlimited" promises we cannot keep.</p>
      </div>
      {err && <p className="mt-8 text-center text-sm text-destructive">Could not load plans right now. Please try again shortly.</p>}
      {!plans && !err && <Spinner label="Loading plans" />}
      <div className="mx-auto mt-10 grid max-w-5xl gap-4 md:grid-cols-3">
        {plans?.map((p) => (
          <Card key={p.key} className={cn(p.key === "pro" && "border-primary ring-1 ring-primary")}>
            <CardHeader>
              <CardTitle>{p.name}</CardTitle>
              <p className="text-3xl font-bold">{p.price_inr === 0 ? "Free" : formatMoney(p.price_inr)}{p.price_inr > 0 && <span className="text-sm font-normal text-muted-foreground"> / month</span>}</p>
              <p className="text-sm text-muted-foreground">{p.description}</p>
            </CardHeader>
            <CardContent className="space-y-4">
              <ul className="space-y-2 text-sm">{p.features.map((f) => <li key={f} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />{f}</li>)}</ul>
              <Link href={p.key === "free" ? "/register" : `/register?plan=${p.key}`} className={cn(buttonVariants({ variant: p.key === "pro" ? "default" : "outline" }), "w-full")}>
                {p.key === "free" ? "Start free" : `Choose ${p.name}`}
              </Link>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
