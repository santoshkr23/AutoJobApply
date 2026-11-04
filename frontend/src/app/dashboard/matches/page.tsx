"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Bookmark, Check, Play, X } from "lucide-react";
import { JobSummary } from "@/components/job-card";
import { Pager } from "@/components/pager";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, EmptyState, PageHeader, Spinner } from "@/components/ui/feedback";
import { Select } from "@/components/ui/form";
import { api, errorMessage, type Match, type Page } from "@/lib/api";
import { titleCase } from "@/lib/utils";

export default function MatchesPage() {
  const router = useRouter();
  const [status, setStatus] = useState("");
  const [min, setMin] = useState("0");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<Match> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    setData(null);
    const qs = new URLSearchParams({ page: String(page), page_size: "10", min_score: min });
    if (status) qs.set("status", status);
    try { setData(await api<Page<Match>>(`/matches?${qs}`)); } catch (e) { setErr(errorMessage(e)); }
  }, [page, status, min]);
  useEffect(() => { void load(); }, [load]);

  async function run() {
    setRunning(true); setErr(null); setNote(null);
    try {
      const r = await api("/matches/run", { method: "POST" });
      setNote(`Scored ${r.evaluated} new job(s): ${r.saved} saved, ${r.below_threshold} below your minimum score${r.quota_blocked ? `, ${r.quota_blocked} held back by your plan's monthly limit` : ""}.`);
      await load();
    } catch (e) { setErr(errorMessage(e)); } finally { setRunning(false); }
  }
  async function setMatchStatus(id: string, s: string) { try { await api(`/matches/${id}`, { method: "PATCH", body: { status: s } }); await load(); } catch (e) { setErr(errorMessage(e)); } }
  async function start(jobId: string) { try { const a = await api("/applications", { body: { job_id: jobId } }); router.push(`/dashboard/applications/${a.id}`); } catch (e) { setErr(errorMessage(e)); } }

  return (
    <>
      <PageHeader title="Matched jobs" description="Scored against your verified profile and preferences."
        actions={<Button onClick={run} loading={running}><Play className="h-4 w-4" />Find new matches</Button>} />
      {note && <Alert tone="success" className="mb-3">{note}</Alert>}
      {err && <Alert tone="error" className="mb-3">{err} {err.includes("profile") && <Link className="underline" href="/dashboard/profile">Open profile</Link>}</Alert>}
      <div className="mb-4 flex flex-wrap gap-2">
        <Select aria-label="Status" className="w-40" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">Active</option><option value="new">New</option><option value="saved">Saved</option><option value="dismissed">Dismissed</option></Select>
        <Select aria-label="Minimum score" className="w-44" value={min} onChange={(e) => { setMin(e.target.value); setPage(1); }}><option value="0">Any score</option><option value="70">70% and up</option><option value="80">80% and up</option><option value="90">90% and up</option></Select>
      </div>
      {!data && !err && <Spinner />}
      {data && data.items.length === 0 && <EmptyState title="No matches yet" action={<Button onClick={run} loading={running}>Find new matches</Button>}>Run matching after your profile is confirmed and a job source has collected jobs.</EmptyState>}
      <div className="space-y-3">
        {data?.items.map((m) => (
          <Card key={m.id}><CardContent className="space-y-3 p-5">
            <JobSummary job={{ ...m.job, match_score: m.score }} />
            <p className="text-sm">{m.explanation}</p>
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <div><p className="mb-1 flex items-center gap-1 font-medium text-success"><Check className="h-3.5 w-3.5" />Skills you have</p><div className="flex flex-wrap gap-1">{m.skills_matched.length ? m.skills_matched.map((s) => <Badge key={s} tone="success">{s}</Badge>) : <span className="text-muted-foreground">None matched</span>}</div></div>
              <div><p className="mb-1 flex items-center gap-1 font-medium text-warning"><X className="h-3.5 w-3.5" />Missing</p><div className="flex flex-wrap gap-1">{m.missing_skills.length ? m.missing_skills.map((s) => <Badge key={s} tone="warning">{s}</Badge>) : <span className="text-muted-foreground">Nothing missing</span>}</div></div>
            </div>
            <p className="text-xs text-muted-foreground">Experience: {titleCase(m.experience_match?.status ?? "unknown")} · Location: {titleCase(m.location_match?.status ?? "unknown")} · Salary: {titleCase(m.salary_match?.status ?? "unknown")} · Recommendation: <strong>{titleCase(m.recommendation)}</strong></p>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => start(m.job.id)}>Start application</Button>
              {m.status !== "saved" && <Button size="sm" variant="outline" onClick={() => setMatchStatus(m.id, "saved")}><Bookmark className="h-3.5 w-3.5" />Save</Button>}
              {m.status !== "dismissed" ? <Button size="sm" variant="ghost" onClick={() => setMatchStatus(m.id, "dismissed")}>Dismiss</Button> : <Button size="sm" variant="ghost" onClick={() => setMatchStatus(m.id, "new")}>Restore</Button>}
            </div>
          </CardContent></Card>
        ))}
      </div>
      {data && <Pager page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
    </>
  );
}
