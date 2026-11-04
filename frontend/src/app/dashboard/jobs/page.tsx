"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Search } from "lucide-react";
import { JobSummary } from "@/components/job-card";
import { Pager } from "@/components/pager";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, EmptyState, PageHeader, Spinner } from "@/components/ui/feedback";
import { Input, Select } from "@/components/ui/form";
import { Modal } from "@/components/ui/modal";
import { api, errorMessage, type Job, type Page } from "@/lib/api";

export default function JobsPage() {
  const router = useRouter();
  const [f, setF] = useState({ q: "", country: "", work_mode: "", posted_within_days: "" });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<Job> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (p: number, filters = f) => {
    setData(null); setErr(null);
    const qs = new URLSearchParams({ page: String(p), page_size: "10" });
    Object.entries(filters).forEach(([k, v]) => v && qs.set(k, v));
    try { setData(await api<Page<Job>>(`/jobs?${qs}`)); } catch (e) { setErr(errorMessage(e)); }
  }, [f]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void load(page); }, [page]);

  async function open(id: string) { try { setDetail(await api(`/jobs/${id}`)); } catch (e) { setErr(errorMessage(e)); } }
  async function track(id: string) {
    setBusy(true);
    try { const a = await api("/applications", { body: { job_id: id } }); router.push(`/dashboard/applications/${a.id}`); } catch (e) { setErr(errorMessage(e)); setBusy(false); }
  }

  return (
    <>
      <PageHeader title="Job discovery" description="Jobs collected from authorized sources. Duplicates and expired postings are hidden." />
      <form className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5" onSubmit={(e) => { e.preventDefault(); setPage(1); void load(1); }} role="search">
        <Input aria-label="Search jobs" placeholder="Search title, company, skill…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} className="lg:col-span-2" />
        <Input aria-label="Country code" placeholder="Country (IN)" maxLength={2} value={f.country} onChange={(e) => setF({ ...f, country: e.target.value.toUpperCase() })} />
        <Select aria-label="Work mode" value={f.work_mode} onChange={(e) => setF({ ...f, work_mode: e.target.value })}><option value="">Any work mode</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="onsite">On-site</option></Select>
        <Button type="submit"><Search className="h-4 w-4" />Search</Button>
      </form>
      {err && <Alert tone="error">{err}</Alert>}
      {!data && !err && <Spinner />}
      {data && data.items.length === 0 && <EmptyState title="No jobs found">Try different filters. An administrator may need to enable a job source.</EmptyState>}
      <div className="space-y-3">
        {data?.items.map((j) => (
          <Card key={j.id}><CardContent className="p-5"><JobSummary job={j}><div className="flex gap-2 pt-1"><Button size="sm" variant="outline" onClick={() => open(j.id)}>Details</Button><Button size="sm" loading={busy} onClick={() => track(j.id)}>Track application</Button></div></JobSummary></CardContent></Card>
        ))}
      </div>
      {data && <Pager page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail?.title ?? ""} wide>
        {detail && <div className="space-y-4 text-sm">
          <p className="text-muted-foreground">{detail.company} · {detail.location_text}</p>
          {detail.analysis?.suspicious_instructions_detected && <Alert tone="warning">This posting contains instruction-like text aimed at AI tools. It was ignored.</Alert>}
          <div><h3 className="font-medium">Required skills</h3><p className="text-muted-foreground">{detail.analysis?.required_skills?.join(", ") || "Not detected"}</p></div>
          {detail.analysis?.preferred_skills?.length > 0 && <div><h3 className="font-medium">Nice to have</h3><p className="text-muted-foreground">{detail.analysis.preferred_skills.join(", ")}</p></div>}
          <div><h3 className="font-medium">Description</h3><p className="max-h-72 overflow-y-auto whitespace-pre-wrap text-muted-foreground">{detail.description}</p></div>
        </div>}
      </Modal>
    </>
  );
}
