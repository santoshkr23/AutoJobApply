"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, FileDown, Send, Sparkles } from "lucide-react";
import { Badge, ScoreBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, Spinner } from "@/components/ui/feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export default function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [a, setA] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [letter, setLetter] = useState<string[] | null>(null);
  const [notes, setNotes] = useState("");
  const [interview, setInterview] = useState("");

  const load = useCallback(async () => {
    try { const d = await api(`/applications/${id}`); setA(d); setNotes(d.notes ?? ""); setInterview(d.interview_at ? d.interview_at.slice(0, 16) : ""); } catch (e) { setErr(errorMessage(e)); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);
  // While the platform is submitting, poll for the outcome.
  useEffect(() => { if (a?.status !== "APPLYING") return; const t = setInterval(load, 3000); return () => clearInterval(t); }, [a?.status, load]);

  async function act(name: string, fn: () => Promise<any>) {
    setBusy(name); setErr(null);
    try { const r = await fn(); if (r) setA(r); await load(); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(null); }
  }
  async function download(kind: string, fmt: string) {
    try { const r = await api(`/applications/${id}/documents/${kind}/${fmt}`); window.open(r.url, "_blank", "noopener"); } catch (e) { setErr(errorMessage(e)); }
  }

  if (!a && !err) return <Spinner />;
  if (!a) return <Alert tone="error">{err}</Alert>;

  const docs: any[] = a.documents ?? [];
  const resume = docs.find((d) => d.kind === "resume");
  const cl = docs.find((d) => d.kind === "cover_letter");
  const allApproved = docs.length === 2 && docs.every((d) => d.status === "approved");
  const terminal = ["REJECTED", "WITHDRAWN"].includes(a.status);
  const changes = [...(resume?.change_log ?? []), ...(cl?.change_log ?? [])];

  return (
    <>
      <Link href="/dashboard/applications" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Applications</Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div><h1 className="text-2xl font-semibold">{a.title}</h1><p className="text-muted-foreground">{a.company}{a.location ? ` · ${a.location}` : ""}</p>
          <p className="mt-2 flex flex-wrap items-center gap-2"><StatusBadge status={a.status} /><ScoreBadge score={a.match_score} />{a.is_sample && <Badge tone="warning">sample job</Badge>}
            <a href={a.job_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">Job posting<ExternalLink className="h-3 w-3" /></a></p></div>
      </div>
      {err && <Alert tone="error" className="mb-4">{err}</Alert>}

      {a.status === "APPLYING" && <Alert className="mb-4" title="Submitting…">The platform is submitting this application. This page updates automatically.</Alert>}
      {a.status === "APPLIED" && <Alert tone="success" className="mb-4" title="Applied">{a.events.find((e: any) => e.to === "APPLIED")?.data?.self_reported ? "You reported applying yourself (not verified by the platform)." : `Submission confirmed by the employer site${a.confirmation_ref ? ` (ref ${a.confirmation_ref})` : ""}.`}</Alert>}
      {a.status === "MANUAL_REQUIRED" && <Alert tone="warning" className="mb-4" title="Your action is needed">{a.failure_reason}{" "}<a className="underline" href={a.job_url} target="_blank" rel="noopener noreferrer">Open the job posting</a>, apply with your approved documents, then mark it as applied below.</Alert>}
      {a.status === "FAILED" && <Alert tone="error" className="mb-4" title="Submission failed">{a.failure_reason ?? "The submission could not be completed."} Nothing was submitted.</Alert>}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card><CardHeader><CardTitle>Application documents</CardTitle><CardDescription>Generated from your verified profile only. Review everything before approving.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              {docs.length === 0 ? <Button onClick={() => act("prepare", () => api(`/applications/${id}/prepare`, { method: "POST" }))} loading={busy === "prepare"}><Sparkles className="h-4 w-4" />Generate tailored resume and cover letter</Button> : (
                <>
                  <div className="flex flex-wrap gap-2">
                    {["resume", "cover_letter"].flatMap((k) => ["pdf", "docx"].map((f) => <Button key={k + f} size="sm" variant="outline" onClick={() => download(k, f)}><FileDown className="h-3.5 w-3.5" />{k === "resume" ? "Resume" : "Cover letter"} .{f}</Button>))}
                    <Badge tone={allApproved ? "success" : "warning"}>{allApproved ? "documents approved" : "draft - not approved"}</Badge>
                  </div>
                  {resume?.resume && <details className="rounded-md border p-3"><summary className="cursor-pointer text-sm font-medium">Resume preview</summary>
                    <div className="mt-3 space-y-3 text-sm"><p className="font-semibold">{resume.resume.full_name}</p><p>{resume.resume.summary}</p><p><strong>Skills:</strong> {resume.resume.skills.join(", ")}</p>
                      {resume.resume.experience.map((e: any) => <div key={e.id}><p className="font-medium">{e.title} - {e.company}</p><ul className="list-disc pl-5 text-muted-foreground">{e.bullets.map((b: string, i: number) => <li key={i}>{b}</li>)}</ul></div>)}</div></details>}
                  <details className="rounded-md border p-3" open><summary className="cursor-pointer text-sm font-medium">Cover letter</summary>
                    <div className="mt-3 space-y-2 text-sm">
                      {letter === null ? <><p>{cl?.content?.greeting}</p>{cl?.content?.paragraphs.map((p: string, i: number) => <p key={i}>{p}</p>)}<p className="whitespace-pre-line">{cl?.content?.closing}</p>
                        <Button size="sm" variant="outline" onClick={() => setLetter(cl?.content?.paragraphs ?? [])}>Edit paragraphs</Button></> : <>
                        <Textarea aria-label="Cover letter paragraphs" rows={10} value={letter.join("\n\n")} onChange={(e) => setLetter(e.target.value.split(/\n{2,}/))} />
                        <div className="flex gap-2"><Button size="sm" loading={busy === "letter"} onClick={() => act("letter", async () => { const r = await api(`/applications/${id}/cover-letter`, { method: "PUT", body: { paragraphs: letter.filter((p) => p.trim()) } }); setLetter(null); return r; })}>Save</Button><Button size="sm" variant="ghost" onClick={() => setLetter(null)}>Cancel</Button></div></>}
                    </div></details>
                  {changes.length > 0 && <details className="rounded-md border p-3"><summary className="cursor-pointer text-sm font-medium">What the AI changed ({changes.length})</summary>
                    <ul className="mt-3 space-y-2 text-sm">{changes.map((c: any, i: number) => <li key={i} className="rounded bg-muted p-2"><Badge tone={c.kind === "rejected" ? "danger" : "primary"}>{c.kind}</Badge> <span className="font-medium">{c.section}</span>{c.reason && <span className="text-muted-foreground"> - {c.reason}</span>}
                      {c.before && <p className="mt-1 text-xs text-muted-foreground line-through">{String(c.before).slice(0, 200)}</p>}{c.after && <p className="mt-1 text-xs">{String(c.after).slice(0, 200)}</p>}</li>)}</ul></details>}
                  {!terminal && ["PENDING_APPROVAL", "MANUAL_REQUIRED", "FAILED", "RESUME_GENERATED", "MATCHED"].includes(a.status) && (
                    <div className="flex flex-wrap gap-2">
                      <Button variant="outline" loading={busy === "prepare"} onClick={() => act("prepare", () => api(`/applications/${id}/prepare`, { method: "POST" }))}><Sparkles className="h-4 w-4" />Regenerate</Button>
                      {!allApproved && <Button loading={busy === "docs"} onClick={() => act("docs", () => api(`/applications/${id}/approve-documents`, { method: "POST" }))}>Approve documents</Button>}
                    </div>)}
                </>
              )}
            </CardContent></Card>

          {allApproved && ["PENDING_APPROVAL", "MANUAL_REQUIRED", "FAILED"].includes(a.status) && (
            <Card><CardHeader><CardTitle>Submit</CardTitle><CardDescription>On supported sites the platform submits for you and only reports success when the site confirms it. Elsewhere you apply yourself with the approved documents.</CardDescription></CardHeader>
              <CardContent className="space-y-3">
                <Alert>Submitting needs the &quot;automated applications&quot; consent in <Link className="underline" href="/dashboard/settings">Settings</Link> and a plan that includes it. By pressing the button you approve submitting <strong>this</strong> application.</Alert>
                <Button loading={busy === "submit"} onClick={() => act("submit", () => api(`/applications/${id}/submit`, { method: "POST" }))}><Send className="h-4 w-4" />Approve and submit</Button>
              </CardContent></Card>
          )}

          <Card><CardHeader><CardTitle>Timeline</CardTitle></CardHeader><CardContent>
            <ol className="space-y-3 border-l pl-4 text-sm">{[...a.events].reverse().map((e: any, i: number) => (
              <li key={i}><p className="font-medium">{e.message ?? e.type}</p><p className="text-xs text-muted-foreground">{formatDateTime(e.at)}{e.to ? ` · → ${e.to.toLowerCase().replace(/_/g, " ")}` : ""}</p></li>))}</ol></CardContent></Card>
        </div>

        <div className="space-y-4">
          <Card><CardHeader><CardTitle>Track outcome</CardTitle></CardHeader><CardContent className="space-y-3">
            <Field label="Update status" htmlFor="st"><Select id="st" value="" onChange={(e) => e.target.value && act("status", () => api(`/applications/${id}`, { method: "PATCH", body: { status: e.target.value } }))}>
              <option value="">Choose…</option><option value="APPLIED">I applied myself</option><option value="INTERVIEW">Interview</option><option value="OFFER">Offer</option><option value="REJECTED">Rejected</option><option value="WITHDRAWN">Withdrawn</option></Select></Field>
            <Field label="Interview date and time" htmlFor="iv"><Input id="iv" type="datetime-local" value={interview} onChange={(e) => setInterview(e.target.value)} onBlur={() => interview && act("iv", () => api(`/applications/${id}`, { method: "PATCH", body: { interview_at: new Date(interview).toISOString() } }))} /></Field>
            <Field label="Notes" htmlFor="notes"><Textarea id="notes" rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={() => notes !== (a.notes ?? "") && act("notes", () => api(`/applications/${id}`, { method: "PATCH", body: { notes } }))} /></Field>
          </CardContent></Card>
          <Button variant="ghost" className="text-destructive" onClick={() => confirm("Remove this application from your list?") && act("del", async () => { await api(`/applications/${id}`, { method: "DELETE" }); router.push("/dashboard/applications"); return null; })}>Remove application</Button>
        </div>
      </div>
    </>
  );
}
