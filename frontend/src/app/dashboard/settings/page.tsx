"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, PageHeader, Spinner } from "@/components/ui/feedback";
import { Checkbox, Field, Input } from "@/components/ui/form";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function SettingsPage() {
  const { user } = useAuth();
  const [consents, setConsents] = useState<Record<string, boolean> | null>(null);
  const [types, setTypes] = useState<Record<string, string>>({});
  const [prefs, setPrefs] = useState<Record<string, { email: boolean; in_app: boolean }> | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [del, setDel] = useState({ password: "", confirm: "" });

  useEffect(() => {
    Promise.all([api("/consents"), api("/notification-types"), api("/notification-preferences")]).then(([c, t, p]) => {
      setConsents(Object.fromEntries(c.map((x: any) => [x.consent_type, x.granted]))); setTypes(t); setPrefs(p);
    }).catch((e) => setMsg({ tone: "error", text: errorMessage(e) }));
  }, []);

  const flash = (tone: "success" | "error", text: string) => setMsg({ tone, text });
  async function setConsent(type: string, granted: boolean) {
    try { await api("/consents", { body: { consent_type: type, granted } }); setConsents((c) => ({ ...c, [type]: granted })); flash("success", "Consent updated."); } catch (e) { flash("error", errorMessage(e)); }
  }
  async function savePrefs() { try { await api("/notification-preferences", { method: "PUT", body: prefs }); flash("success", "Notification preferences saved."); } catch (e) { flash("error", errorMessage(e)); } }
  async function changePassword(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget); const form = e.currentTarget;
    try { await api("/auth/change-password", { body: { current_password: f.get("cur"), new_password: f.get("new") } }); form.reset(); flash("success", "Password changed. Other sessions were signed out."); } catch (er) { flash("error", errorMessage(er)); }
  }
  async function deleteAccount() {
    if (del.confirm !== "DELETE") return flash("error", 'Type DELETE to confirm.');
    try { await api("/me", { method: "DELETE", body: { password: del.password || null, confirm: del.confirm } }); window.location.href = "/"; } catch (e) { flash("error", errorMessage(e)); }
  }

  if (!consents || !prefs) return msg ? <Alert tone="error">{msg.text}</Alert> : <Spinner />;
  return (
    <>
      <PageHeader title="Settings" />
      {msg && <Alert tone={msg.tone} className="mb-4">{msg.text}</Alert>}
      <div className="max-w-2xl space-y-6">
        <Card><CardHeader><CardTitle>Consents</CardTitle><CardDescription>Withdrawing a consent takes effect immediately and is recorded.</CardDescription></CardHeader><CardContent className="space-y-3">
          <Checkbox checked={!!consents.ai_processing} onChange={(e) => setConsent("ai_processing", e.target.checked)} label="AI processing of my resume and job descriptions" />
          <Checkbox checked={!!consents.auto_apply} onChange={(e) => setConsent("auto_apply", e.target.checked)} label="Automated applications (each one still needs my approval)" />
          <Checkbox checked={!!consents.marketing} onChange={(e) => setConsent("marketing", e.target.checked)} label="Product updates by email" /></CardContent></Card>
        <Card><CardHeader><CardTitle>Notifications</CardTitle></CardHeader><CardContent className="space-y-3">
          <table className="w-full text-sm"><thead><tr className="text-left text-xs text-muted-foreground"><th className="py-1">Event</th><th>Email</th><th>In-app</th></tr></thead><tbody>{Object.entries(types).map(([k, label]) => (
            <tr key={k} className="border-t"><td className="py-2">{label}</td>{(["email", "in_app"] as const).map((ch) => <td key={ch}><input aria-label={`${label} ${ch}`} type="checkbox" className="h-4 w-4 accent-[hsl(var(--primary))]" checked={prefs[k]?.[ch] ?? true} onChange={(e) => setPrefs({ ...prefs, [k]: { ...(prefs[k] ?? { email: true, in_app: true }), [ch]: e.target.checked } })} /></td>)}</tr>))}</tbody></table>
          <Button onClick={savePrefs}>Save notification settings</Button></CardContent></Card>
        {user?.has_password && <Card><CardHeader><CardTitle>Change password</CardTitle></CardHeader><CardContent>
          <form onSubmit={changePassword} className="space-y-3"><Field label="Current password" htmlFor="cur"><Input id="cur" name="cur" type="password" required autoComplete="current-password" /></Field>
            <Field label="New password" htmlFor="new" hint="At least 10 characters with letters and numbers."><Input id="new" name="new" type="password" required minLength={10} autoComplete="new-password" /></Field><Button type="submit">Change password</Button></form></CardContent></Card>}
        <Card className="border-destructive/50"><CardHeader><CardTitle className="text-destructive">Delete account</CardTitle><CardDescription>Permanently removes your personal data, resumes and documents. Payment records are kept as required by law.</CardDescription></CardHeader><CardContent className="space-y-3">
          {user?.has_password && <Field label="Password" htmlFor="dp"><Input id="dp" type="password" value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} /></Field>}
          <Field label='Type "DELETE" to confirm' htmlFor="dc"><Input id="dc" value={del.confirm} onChange={(e) => setDel({ ...del, confirm: e.target.value })} /></Field>
          <Button variant="destructive" onClick={deleteAccount}>Delete my account</Button></CardContent></Card>
      </div>
    </>
  );
}
