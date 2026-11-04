"use client";

import { useCallback, useEffect, useState } from "react";
import { FileUp, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, EmptyState, PageHeader, Spinner } from "@/components/ui/feedback";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export default function ResumesPage() {
  const [items, setItems] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => { try { setItems(await api("/resumes")); } catch (e) { setErr(errorMessage(e)); } }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (!items?.some((r) => r.parse_status === "pending")) return; const t = setInterval(load, 2500); return () => clearInterval(t); }, [items, load]);

  async function upload(file: File) {
    setBusy(true); setErr(null);
    try { const fd = new FormData(); fd.append("file", file); await api("/resumes", { form: fd }); await load(); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }
  async function download(id: string) { try { const r = await api(`/resumes/${id}/download`); window.open(r.url, "_blank", "noopener"); } catch (e) { setErr(errorMessage(e)); } }
  async function remove(id: string) { if (!confirm("Delete this resume file?")) return; try { await api(`/resumes/${id}`, { method: "DELETE" }); await load(); } catch (e) { setErr(errorMessage(e)); } }

  return (
    <>
      <PageHeader title="Resumes" description="Your uploaded resumes. Edit the verified details on the Profile page."
        actions={<label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"><FileUp className="h-4 w-4" />{busy ? "Uploading…" : "Upload resume"}<input type="file" className="sr-only" accept=".pdf,.docx" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></label>} />
      {err && <Alert tone="error" className="mb-4">{err}</Alert>}
      {!items && !err && <Spinner />}
      {items?.length === 0 && <EmptyState title="No resumes uploaded" />}
      <div className="space-y-3">{items?.map((r) => (
        <Card key={r.id}><CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
          <div><p className="font-medium">{r.original_filename}</p><p className="text-sm text-muted-foreground">{(r.size_bytes / 1024).toFixed(0)} KB · uploaded {formatDate(r.created_at)}</p>
            <div className="mt-2 flex gap-2"><Badge tone={r.parse_status === "failed" ? "danger" : r.parse_status === "pending" ? "warning" : "success"}>{r.parse_status}</Badge>{r.confirmed_at && <Badge tone="primary">verified</Badge>}</div>
            {r.parse_error && <p className="mt-2 text-sm text-destructive">{r.parse_error}</p>}</div>
          <div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => download(r.id)}>Download</Button>
            <Button variant="ghost" size="sm" onClick={() => api(`/resumes/${r.id}/reparse`, { method: "POST" }).then(load).catch((e) => setErr(errorMessage(e)))}>Re-read</Button>
            <Button variant="ghost" size="icon" aria-label="Delete resume" onClick={() => remove(r.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button></div>
        </CardContent></Card>))}</div>
    </>
  );
}
