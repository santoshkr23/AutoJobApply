"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, EmptyState, PageHeader, Spinner } from "@/components/ui/feedback";
import { api, errorMessage } from "@/lib/api";
import { cn, formatDateTime } from "@/lib/utils";

export default function NotificationsPage() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(async () => { try { setD(await api("/notifications?limit=50")); } catch (e) { setErr(errorMessage(e)); } }, []);
  useEffect(() => { void load(); }, [load]);
  if (err) return <Alert tone="error">{err}</Alert>;
  if (!d) return <Spinner />;
  return (
    <>
      <PageHeader title="Notifications" description={`${d.unread} unread`} actions={d.unread > 0 && <Button variant="outline" size="sm" onClick={() => api("/notifications/read-all", { method: "POST" }).then(load)}>Mark all read</Button>} />
      {d.items.length === 0 && <EmptyState title="Nothing here yet" />}
      <div className="space-y-2">{d.items.map((n: any) => (
        <Card key={n.id} className={cn(!n.read && "border-primary/50")}><CardContent className="flex items-start justify-between gap-3 p-4">
          <div><p className={cn("text-sm", !n.read && "font-semibold")}>{n.title}</p><p className="text-sm text-muted-foreground">{n.body}</p><p className="mt-1 text-xs text-muted-foreground">{formatDateTime(n.created_at)}</p></div>
          {!n.read && <Button size="sm" variant="ghost" onClick={() => api(`/notifications/${n.id}/read`, { method: "POST" }).then(load)}>Mark read</Button>}</CardContent></Card>))}</div>
    </>
  );
}
