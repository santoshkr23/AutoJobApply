"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Download } from "lucide-react";
import { Pager } from "@/components/pager";
import { ScoreBadge, StatusBadge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Alert, EmptyState, PageHeader, Spinner } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/form";
import { api, errorMessage, type AppRow, type Page } from "@/lib/api";
import { cn, formatDate, titleCase } from "@/lib/utils";

const STATUSES = ["DISCOVERED", "MATCHED", "RESUME_GENERATED", "PENDING_APPROVAL", "APPLYING", "APPLIED", "MANUAL_REQUIRED", "FAILED", "REJECTED", "INTERVIEW", "OFFER", "WITHDRAWN"];

function List() {
  const sp = useSearchParams();
  const [status, setStatus] = useState(sp.get("status") ?? "");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<AppRow> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    const qs = new URLSearchParams({ page: String(page), page_size: "15" });
    if (status) qs.set("status", status);
    if (q.trim()) qs.set("q", q.trim());
    try { setData(await api<Page<AppRow>>(`/applications?${qs}`)); } catch (e) { setErr(errorMessage(e)); }
  }, [page, status, q]);
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [load]);

  return (
    <>
      <PageHeader title="Applications" description="Every application and where it stands."
        actions={<>
          <a className={cn(buttonVariants({ variant: "outline", size: "sm" }))} href="/api/applications/export.csv" download><Download className="h-4 w-4" />CSV</a>
          <a className={cn(buttonVariants({ variant: "outline", size: "sm" }))} href="/api/applications/export.xlsx" download><Download className="h-4 w-4" />Excel</a>
        </>} />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input aria-label="Search applications" placeholder="Search title or company…" className="max-w-xs" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <Select aria-label="Status" className="w-52" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">All statuses</option>{STATUSES.map((s) => <option key={s} value={s}>{titleCase(s.toLowerCase())}</option>)}</Select>
      </div>
      {err && <Alert tone="error">{err}</Alert>}
      {!data && !err && <Spinner />}
      {data && data.items.length === 0 && <EmptyState title="No applications">Start one from <Link className="underline" href="/dashboard/matches">your matched jobs</Link>.</EmptyState>}
      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted text-xs uppercase text-muted-foreground"><tr><th className="p-3">Job</th><th className="p-3">Status</th><th className="hidden p-3 md:table-cell">Match</th><th className="hidden p-3 md:table-cell">Updated</th><th className="p-3"><span className="sr-only">Open</span></th></tr></thead>
            <tbody className="divide-y">{data.items.map((a) => (
              <tr key={a.id} className="hover:bg-muted/50">
                <td className="p-3"><p className="font-medium">{a.title}</p><p className="text-muted-foreground">{a.company}</p></td>
                <td className="p-3"><StatusBadge status={a.status} />{a.needs_user_action && <p className="mt-1 text-xs text-warning">Needs you</p>}</td>
                <td className="hidden p-3 md:table-cell"><ScoreBadge score={a.match_score} /></td>
                <td className="hidden p-3 text-muted-foreground md:table-cell">{formatDate(a.updated_at)}</td>
                <td className="p-3 text-right"><Link className="text-primary hover:underline" href={`/dashboard/applications/${a.id}`}>Open</Link></td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
      {data && <Pager page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
    </>
  );
}

export default function ApplicationsPage() { return <Suspense><List /></Suspense>; }
