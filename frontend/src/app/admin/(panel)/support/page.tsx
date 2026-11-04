"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, EmptyState, PageHeader, Spinner } from "@/components/ui/feedback";
import { adminApi, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export default function AdminSupport() {
  const [items, setItems] = useState<any[] | null>(null); const [err, setErr] = useState<string | null>(null);
  const load = useCallback(async () => { try { setItems(await adminApi("/support?status=open")); } catch (e) { setErr(errorMessage(e)); } }, []);
  useEffect(() => { void load(); }, [load]);
  if (!items) return err ? <Alert tone="error">{err}</Alert> : <Spinner />;
  return (
    <>
      <PageHeader title="Support requests" description="Open requests from the contact form." />
      {items.length === 0 && <EmptyState title="Inbox zero" />}
      <div className="space-y-3">{items.map((r) => <Card key={r.id}><CardContent className="space-y-2 p-5"><div className="flex flex-wrap justify-between gap-2"><div><p className="font-medium">{r.subject}</p><p className="text-sm text-muted-foreground"><a className="underline" href={`mailto:${r.email}`}>{r.email}</a> · {formatDateTime(r.created_at)}</p></div>
        <Button size="sm" variant="outline" onClick={() => adminApi(`/support/${r.id}`, { method: "PATCH" }).then(load)}>Mark closed</Button></div><p className="whitespace-pre-wrap text-sm">{r.message}</p></CardContent></Card>)}</div>
    </>
  );
}
