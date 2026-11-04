"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, PageHeader, Spinner } from "@/components/ui/feedback";
import { Checkbox, Field, Input } from "@/components/ui/form";
import { adminApi, errorMessage } from "@/lib/api";
import { titleCase } from "@/lib/utils";

export default function AdminSystem() {
  const [flags, setFlags] = useState<any[] | null>(null); const [w, setW] = useState<Record<string, number> | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  useEffect(() => { adminApi("/feature-flags").then(setFlags).catch((e) => setMsg({ tone: "error", text: errorMessage(e) })); adminApi("/settings/matching-weights").then(setW).catch(() => undefined); }, []);
  async function flag(f: any, enabled: boolean) { try { await adminApi(`/feature-flags/${f.key}`, { method: "PUT", body: { enabled } }); setFlags((fs) => fs!.map((x) => (x.key === f.key ? { ...x, enabled } : x))); } catch (e) { setMsg({ tone: "error", text: errorMessage(e) }); } }
  async function saveW() { try { setW(await adminApi("/settings/matching-weights", { method: "PUT", body: w })); setMsg({ tone: "success", text: "Matching weights saved. They apply to the next matching run." }); } catch (e) { setMsg({ tone: "error", text: errorMessage(e) }); } }
  if (!flags || !w) return <Spinner />;
  return (
    <>
      <PageHeader title="System" />
      {msg && <Alert tone={msg.tone} className="mb-4">{msg.text}</Alert>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Feature flags</CardTitle></CardHeader><CardContent className="space-y-3">{flags.map((f) => <Checkbox key={f.key} checked={f.enabled} onChange={(e) => flag(f, e.target.checked)} label={<><strong>{f.key}</strong>{f.description ? ` - ${f.description}` : ""}</>} />)}{flags.length === 0 && <p className="text-sm text-muted-foreground">No flags defined.</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle>Matching weights</CardTitle><CardDescription>Relative importance of each component (0-100).</CardDescription></CardHeader><CardContent className="space-y-3">
          {Object.entries(w).map(([k, v]) => <Field key={k} label={titleCase(k)} htmlFor={`w-${k}`}><Input id={`w-${k}`} type="number" min={0} max={100} value={v} onChange={(e) => setW({ ...w, [k]: Number(e.target.value) })} /></Field>)}<Button onClick={saveW}>Save weights</Button></CardContent></Card>
      </div>
    </>
  );
}
