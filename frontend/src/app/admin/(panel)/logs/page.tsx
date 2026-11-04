"use client";

import { useEffect, useState } from "react";
import { Pager } from "@/components/pager";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, PageHeader, Spinner } from "@/components/ui/feedback";
import { Input } from "@/components/ui/form";
import { adminApi, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export default function AdminLogs() {
  const [action, setAction] = useState(""); const [page, setPage] = useState(1);
  const [logs, setLogs] = useState<any>(null); const [failed, setFailed] = useState<any[]>([]); const [err, setErr] = useState<string | null>(null);
  useEffect(() => { const t = setTimeout(() => adminApi(`/audit-logs?page=${page}&action=${encodeURIComponent(action)}`).then(setLogs).catch((e) => setErr(errorMessage(e))), 250); return () => clearTimeout(t); }, [page, action]);
  useEffect(() => { adminApi("/failed-tasks").then(setFailed).catch(() => undefined); }, []);
  return (
    <>
      <PageHeader title="Logs" />
      {err && <Alert tone="error" className="mb-3">{err}</Alert>}
      <Card className="mb-6"><CardHeader><CardTitle>Failed background tasks ({failed.length})</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
        {failed.length === 0 ? <p className="text-muted-foreground">No failures recorded.</p> : failed.map((f, i) => <div key={i} className="rounded bg-muted p-2"><p className="font-mono text-xs">{f.task} · {formatDateTime(f.at)}</p><p className="text-destructive">{f.error}</p></div>)}</CardContent></Card>
      <h2 className="mb-2 text-lg font-semibold">Audit log</h2>
      <Input aria-label="Filter by action prefix" placeholder="Filter by action, e.g. auth. or admin." className="mb-3 max-w-sm" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} />
      {!logs ? <Spinner /> : <div className="overflow-x-auto rounded-lg border"><table className="w-full text-left text-xs"><thead className="bg-muted uppercase text-muted-foreground"><tr><th className="p-2">When</th><th className="p-2">Actor</th><th className="p-2">Action</th><th className="p-2">Target</th><th className="p-2">IP</th></tr></thead>
        <tbody className="divide-y">{logs.items.map((l: any, i: number) => <tr key={i}><td className="whitespace-nowrap p-2">{formatDateTime(l.at)}</td><td className="p-2">{l.actor_type}</td><td className="p-2 font-mono">{l.action}</td><td className="p-2">{l.target}</td><td className="p-2">{l.ip}</td></tr>)}</tbody></table></div>}
      {logs && <Pager page={page} pageSize={50} total={logs.total} onPage={setPage} />}
    </>
  );
}
