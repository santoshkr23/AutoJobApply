"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, PageHeader, Spinner } from "@/components/ui/feedback";
import { adminApi, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export default function AdminSources() {
  const [items, setItems] = useState<any[] | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(async () => { try { setItems(await adminApi("/sources")); } catch (e) { setMsg({ tone: "error", text: errorMessage(e) }); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function toggle(s: any) { try { await adminApi(`/sources/${s.id}`, { method: "PATCH", body: { enabled: !s.enabled } }); await load(); } catch (e) { setMsg({ tone: "error", text: errorMessage(e) }); } }
  async function run(s: any) {
    setBusy(s.id); setMsg(null);
    try { const r = await adminApi(`/sources/${s.id}/run`, { method: "POST" }); setMsg({ tone: r.status === "success" ? "success" : "error", text: `${s.name}: ${r.status} - fetched ${r.fetched}, new ${r.created}, updated ${r.updated}${r.error ? `. ${r.error}` : ""}` }); await load(); }
    catch (e) { setMsg({ tone: "error", text: errorMessage(e) }); } finally { setBusy(null); }
  }
  if (!items) return <Spinner />;
  return (
    <>
      <PageHeader title="Job sources" description="Enable only sources whose terms permit automated access. Real sources are disabled by default." />
      {msg && <Alert tone={msg.tone} className="mb-4">{msg.text}</Alert>}
      <div className="overflow-x-auto rounded-lg border"><table className="w-full text-left text-sm"><thead className="bg-muted text-xs uppercase text-muted-foreground"><tr><th className="p-3">Source</th><th className="p-3">Health</th><th className="p-3">Last run</th><th className="p-3" /></tr></thead>
        <tbody className="divide-y">{items.map((s) => <tr key={s.id}><td className="p-3"><p className="font-medium">{s.name}</p><p className="text-xs text-muted-foreground">{s.connector_type}{s.terms_note ? ` · ${s.terms_note}` : ""}</p></td>
          <td className="p-3"><Badge tone={s.enabled ? "success" : "default"}>{s.enabled ? "enabled" : "disabled"}</Badge>{s.last_status && <Badge className="ml-1" tone={s.last_status === "success" ? "success" : "danger"}>{s.last_status}</Badge>}{s.consecutive_failures > 0 && <p className="mt-1 text-xs text-destructive">{s.consecutive_failures} failure(s): {s.last_error}</p>}</td>
          <td className="p-3">{formatDateTime(s.last_run_at)}</td>
          <td className="space-x-2 p-3 text-right"><Button size="sm" variant="outline" onClick={() => toggle(s)}>{s.enabled ? "Disable" : "Enable"}</Button><Button size="sm" loading={busy === s.id} onClick={() => run(s)}>Run now</Button></td></tr>)}</tbody></table></div>
    </>
  );
}
