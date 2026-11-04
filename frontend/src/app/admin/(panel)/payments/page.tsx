"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Alert, PageHeader, Spinner } from "@/components/ui/feedback";
import { adminApi, errorMessage } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/utils";

export default function AdminPayments() {
  const [items, setItems] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(async () => { try { setItems(await adminApi("/payments")); } catch (e) { setErr(errorMessage(e)); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function refund(p: any) {
    if (!confirm(`Refund the full remaining amount of ${p.invoice_number}?`)) return;
    try { await adminApi(`/payments/${p.id}/refund`, { method: "POST", body: {} }); await load(); } catch (e) { setErr(errorMessage(e)); }
  }
  if (!items) return err ? <Alert tone="error">{err}</Alert> : <Spinner />;
  return (
    <>
      <PageHeader title="Payments" />
      {err && <Alert tone="error" className="mb-3">{err}</Alert>}
      <div className="overflow-x-auto rounded-lg border"><table className="w-full text-left text-sm"><thead className="bg-muted text-xs uppercase text-muted-foreground"><tr><th className="p-3">Invoice</th><th className="p-3">Provider</th><th className="p-3">Amount</th><th className="p-3">Status</th><th className="p-3">Date</th><th className="p-3" /></tr></thead>
        <tbody className="divide-y">{items.map((p) => <tr key={p.id}><td className="p-3 font-mono text-xs">{p.invoice_number ?? "-"}</td><td className="p-3">{p.provider}</td><td className="p-3">{formatMoney(p.amount, p.currency)}{p.refunded_amount > 0 && <span className="text-xs text-muted-foreground"> (refunded {formatMoney(p.refunded_amount, p.currency)})</span>}</td>
          <td className="p-3"><Badge tone={p.status === "succeeded" ? "success" : p.status === "failed" ? "danger" : "warning"}>{p.status}</Badge></td><td className="p-3">{formatDate(p.paid_at)}</td>
          <td className="p-3 text-right">{["succeeded", "partially_refunded"].includes(p.status) && <Button size="sm" variant="outline" onClick={() => refund(p)}>Refund</Button>}</td></tr>)}</tbody></table></div>
      {items.length === 0 && <p className="mt-4 text-sm text-muted-foreground">No payments yet.</p>}
    </>
  );
}
