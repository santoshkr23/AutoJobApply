"use client";

import { useCallback, useEffect, useState } from "react";
import { Pager } from "@/components/pager";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, PageHeader, Spinner } from "@/components/ui/feedback";
import { Input } from "@/components/ui/form";
import { adminApi, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export default function AdminUsers() {
  const [q, setQ] = useState(""); const [page, setPage] = useState(1);
  const [d, setD] = useState<any>(null); const [err, setErr] = useState<string | null>(null);
  const load = useCallback(async () => { try { setD(await adminApi(`/users?page=${page}&q=${encodeURIComponent(q)}`)); } catch (e) { setErr(errorMessage(e)); } }, [page, q]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
  async function toggle(u: any) {
    if (!confirm(`${u.is_active ? "Disable" : "Enable"} ${u.email}?`)) return;
    try { await adminApi(`/users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } }); await load(); } catch (e) { setErr(errorMessage(e)); }
  }
  return (
    <>
      <PageHeader title="Users" />
      <Input aria-label="Search users" placeholder="Search email or name…" className="mb-4 max-w-sm" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      {err && <Alert tone="error" className="mb-3">{err}</Alert>}
      {!d ? <Spinner /> : <div className="overflow-x-auto rounded-lg border"><table className="w-full text-left text-sm"><thead className="bg-muted text-xs uppercase text-muted-foreground"><tr><th className="p-3">User</th><th className="p-3">Plan</th><th className="p-3">Status</th><th className="p-3">Joined</th><th className="p-3" /></tr></thead>
        <tbody className="divide-y">{d.items.map((u: any) => <tr key={u.id}><td className="p-3"><p className="font-medium">{u.email}</p><p className="text-muted-foreground">{u.full_name}</p></td><td className="p-3"><Badge tone="primary">{u.plan}</Badge></td>
          <td className="p-3"><Badge tone={u.is_active ? "success" : "danger"}>{u.is_active ? "active" : "disabled"}</Badge>{!u.verified && <Badge className="ml-1" tone="warning">unverified</Badge>}</td><td className="p-3">{formatDate(u.created_at)}</td>
          <td className="p-3 text-right"><Button size="sm" variant="outline" onClick={() => toggle(u)}>{u.is_active ? "Disable" : "Enable"}</Button></td></tr>)}</tbody></table></div>}
      {d && <Pager page={page} pageSize={d.page_size} total={d.total} onPage={setPage} />}
    </>
  );
}
