"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, PageHeader, Spinner } from "@/components/ui/feedback";
import { adminApi, errorMessage } from "@/lib/api";
import { formatMoney, titleCase } from "@/lib/utils";

export default function AdminOverview() {
  const [s, setS] = useState<any>(null);
  const [h, setH] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { adminApi("/stats").then(setS).catch((e) => setErr(errorMessage(e))); adminApi("/health").then(setH).catch(() => undefined); }, []);
  if (err) return <Alert tone="error">{err}</Alert>;
  if (!s) return <Spinner />;
  const tiles = [["Users", s.users.total], ["Verified", s.users.verified], ["Active jobs", s.jobs.active], ["Matches", s.matches], ["Failed tasks", s.failed_tasks], ["Open support", s.open_support], ["MRR (real providers)", formatMoney(s.mrr_inr_paise)]];
  return (
    <>
      <PageHeader title="Overview" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{tiles.map(([l, v]) => <Card key={String(l)}><CardContent className="p-5"><p className="text-sm text-muted-foreground">{l}</p><p className="text-2xl font-bold">{v}</p></CardContent></Card>)}</div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Applications by status</CardTitle></CardHeader><CardContent className="space-y-1 text-sm">{Object.entries(s.applications).map(([k, v]: any) => <p key={k} className="flex justify-between"><span>{titleCase(k.toLowerCase())}</span><span>{v}</span></p>)}{Object.keys(s.applications).length === 0 && <p className="text-muted-foreground">None yet.</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle>System health</CardTitle></CardHeader><CardContent className="space-y-1 text-sm">{h ? Object.entries(h).map(([k, v]) => <p key={k} className="flex justify-between gap-4"><span>{titleCase(k)}</span><span className="text-right text-muted-foreground">{Array.isArray(v) ? v.join(", ") || "none" : String(v)}</span></p>) : <Spinner />}</CardContent></Card>
      </div>
    </>
  );
}
