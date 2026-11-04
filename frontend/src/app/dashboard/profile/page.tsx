"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, PageHeader, Spinner } from "@/components/ui/feedback";
import { Checkbox, Field, Input } from "@/components/ui/form";
import { ProfileEditor, cleanProfile, emptyProfile, type ProfileData } from "@/components/profile-editor";
import { api, errorMessage } from "@/lib/api";

const MODES = ["remote", "hybrid", "onsite"];
const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function ProfilePage() {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [prefs, setPrefs] = useState<any>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api("/profile").then((p) => setProfile({ ...emptyProfile(), ...p })).catch((e) => setMsg({ tone: "error", text: errorMessage(e) }));
    api("/preferences").then(setPrefs).catch(() => setPrefs({ target_titles: [], required_skills: [], countries: [], cities: [], work_modes: [], salary_min: null, salary_currency: "INR", needs_visa_sponsorship: false, open_to_relocation: false, min_match_score: 70, require_approval: true }));
  }, []);

  async function save(kind: "profile" | "prefs") {
    setBusy(kind); setMsg(null);
    try {
      if (kind === "profile") await api("/profile", { method: "PUT", body: cleanProfile(profile!) });
      else await api("/preferences", { method: "PUT", body: { ...prefs, countries: prefs.countries.map((c: string) => c.toUpperCase()) } });
      setMsg({ tone: "success", text: kind === "profile" ? "Profile saved. Future documents use these details." : "Preferences saved." });
    } catch (e) { setMsg({ tone: "error", text: errorMessage(e) }); } finally { setBusy(null); }
  }

  if (!profile || !prefs) return <Spinner />;
  return (
    <>
      <PageHeader title="Profile and preferences" description="This verified profile is the only source of facts for AI-written documents." />
      {msg && <Alert tone={msg.tone} className="mb-4">{msg.text}</Alert>}
      <div className="space-y-6">
        <Card><CardHeader><CardTitle>Verified profile</CardTitle></CardHeader><CardContent className="space-y-6"><ProfileEditor value={profile} onChange={setProfile} /><Button onClick={() => save("profile")} loading={busy === "profile"}>Save profile</Button></CardContent></Card>
        <Card><CardHeader><CardTitle>Job preferences</CardTitle><CardDescription>Applied the next time you run matching.</CardDescription></CardHeader><CardContent className="space-y-4">
          <Field label="Target job titles" htmlFor="t"><Input id="t" value={prefs.target_titles.join(", ")} onChange={(e) => setPrefs({ ...prefs, target_titles: csv(e.target.value) })} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Countries (codes)" htmlFor="c"><Input id="c" value={prefs.countries.join(", ")} onChange={(e) => setPrefs({ ...prefs, countries: csv(e.target.value) })} /></Field>
            <Field label="Cities" htmlFor="ci"><Input id="ci" value={prefs.cities.join(", ")} onChange={(e) => setPrefs({ ...prefs, cities: csv(e.target.value) })} /></Field>
            <Field label="Minimum salary / year" htmlFor="sa"><Input id="sa" type="number" min={0} value={prefs.salary_min ?? ""} onChange={(e) => setPrefs({ ...prefs, salary_min: e.target.value ? Number(e.target.value) : null })} /></Field>
            <Field label={`Minimum match score: ${prefs.min_match_score}%`} htmlFor="ms"><input id="ms" type="range" min={40} max={95} step={5} className="w-full accent-[hsl(var(--primary))]" value={prefs.min_match_score} onChange={(e) => setPrefs({ ...prefs, min_match_score: Number(e.target.value) })} /></Field>
          </div>
          <fieldset className="flex flex-wrap gap-4"><legend className="mb-1 text-sm font-medium">Work mode</legend>{MODES.map((m) => <Checkbox key={m} label={m} checked={prefs.work_modes.includes(m)} onChange={(e) => setPrefs({ ...prefs, work_modes: e.target.checked ? [...prefs.work_modes, m] : prefs.work_modes.filter((x: string) => x !== m) })} />)}</fieldset>
          <Checkbox label="I need visa sponsorship" checked={prefs.needs_visa_sponsorship} onChange={(e) => setPrefs({ ...prefs, needs_visa_sponsorship: e.target.checked })} />
          <Checkbox label="Open to relocation" checked={prefs.open_to_relocation} onChange={(e) => setPrefs({ ...prefs, open_to_relocation: e.target.checked })} />
          <Button onClick={() => save("prefs")} loading={busy === "prefs"}>Save preferences</Button></CardContent></Card>
      </div>
    </>
  );
}
