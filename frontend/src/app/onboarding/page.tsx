"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, FileUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select } from "@/components/ui/form";
import { Alert, Spinner } from "@/components/ui/feedback";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ProfileEditor, cleanProfile, emptyProfile, type ProfileData } from "@/components/profile-editor";
import { Logo } from "@/components/public-shell";
import { ListInput } from "@/components/list-input";
import { parseCountries } from "@/lib/countries";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

function suggestTitles(p: ProfileData): string[] {
  const out: string[] = [];
  for (const t of [p.headline, ...(p.experience ?? []).map((e) => e.title)]) {
    const v = (t ?? "").trim();
    if (v && v.length <= 60 && !out.some((x) => x.toLowerCase() === v.toLowerCase())) out.push(v);
  }
  return out.slice(0, 3);
}

const STEPS = ["Upload resume", "Extraction", "Verify details", "Preferences", "Match threshold", "Consent"];
const MODES = ["remote", "hybrid", "onsite"];

type Prefs = { target_titles: string[]; required_skills: string[]; countries: string[]; cities: string[]; work_modes: string[]; salary_min: number | null; salary_currency: string; needs_visa_sponsorship: boolean; open_to_relocation: boolean; min_match_score: number };

export default function Onboarding() {
  const router = useRouter();
  const { user, loading, refresh } = useAuth();
  const [step, setStep] = useState(0);
  const [resumeId, setResumeId] = useState<string | null>(null);
  const [profile, setProfile] = useState<ProfileData>(emptyProfile());
  const [prefs, setPrefs] = useState<Prefs>({ target_titles: [], required_skills: [], countries: [], cities: [], work_modes: [], salary_min: null, salary_currency: "INR", needs_visa_sponsorship: false, open_to_relocation: false, min_match_score: 70 });
  const [autoApply, setAutoApply] = useState(false);
  const [aiConsent, setAiConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const poll = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => { if (!loading && !user) router.replace("/login?next=/onboarding"); if (user?.onboarding_completed) router.replace("/dashboard"); }, [loading, user, router]);
  useEffect(() => () => clearInterval(poll.current), []);

  const startPolling = useCallback((id: string) => {
    clearInterval(poll.current);
    poll.current = setInterval(async () => {
      try {
        const r = await api(`/resumes/${id}`);
        if (r.parse_status === "parsed" || r.parse_status === "confirmed") { clearInterval(poll.current); setProfile({ ...emptyProfile(), ...r.parsed_data, country: r.parsed_data?.country ?? null }); setStep(2); }
        else if (r.parse_status === "failed") { clearInterval(poll.current); setErr(r.parse_error || "We could not read this file."); setStep(0); }
      } catch (e) { clearInterval(poll.current); setErr(errorMessage(e)); setStep(0); }
    }, 1500);
  }, []);

  // Pick up where the person left off (page refresh, closed tab) instead of asking for the resume again.
  const resumed = useRef(false);
  useEffect(() => {
    if (loading || !user || resumed.current) return;
    resumed.current = true;
    (async () => {
      try {
        const list = await api("/resumes");
        const r = Array.isArray(list) ? list[0] : null;
        if (!r) return;
        setResumeId(r.id);
        if (r.parse_status === "pending" || r.parse_status === "parsing") { setStep(1); startPolling(r.id); return; }
        if (r.parse_status === "failed") { await api(`/resumes/${r.id}`, { method: "DELETE" }).catch(() => undefined); setResumeId(null); return; }
        const full = await api(`/resumes/${r.id}`);
        setProfile({ ...emptyProfile(), ...full.parsed_data, country: full.parsed_data?.country ?? null });
        if (r.parse_status === "confirmed") {
          const pr = await api("/preferences").catch(() => null);
          if (pr) setPrefs((p) => ({ ...p, ...Object.fromEntries(Object.entries(pr).filter(([, v]) => v !== null && v !== undefined)) }));
          setStep(3);
        } else setStep(2);
      } catch { /* start from the beginning */ }
    })();
  }, [loading, user, startPolling]);

  async function upload(file: File) {
    setErr(null); setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const r = await api("/resumes", { form: fd });
      setResumeId(r.id); setStep(1); startPolling(r.id);
    } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }

  async function confirmProfile() {
    if (!resumeId) return;
    setBusy(true); setErr(null);
    try { await api(`/resumes/${resumeId}/confirm`, { body: cleanProfile(profile) });
      setPrefs((p) => ({
        ...p,
        target_titles: p.target_titles.length ? p.target_titles : suggestTitles(profile),
        required_skills: p.required_skills.length ? p.required_skills : (profile.skills ?? []).slice(0, 8),
      }));
      setStep(3); }
    catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }

  async function savePrefs(next: number) {
    setBusy(true); setErr(null);
    try { await api("/preferences", { method: "PUT", body: { ...prefs, countries: prefs.countries.map((c) => c.toUpperCase()) } }); setStep(next); }
    catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }

  async function finish() {
    if (!aiConsent) { setErr("AI processing consent is needed to analyse your resume and jobs."); return; }
    setBusy(true); setErr(null);
    try {
      await api("/consents", { body: { consent_type: "ai_processing", granted: true } });
      await api("/consents", { body: { consent_type: "auto_apply", granted: autoApply } });
      await api("/onboarding/complete", { method: "POST" });
      await refresh();
      router.push("/dashboard");
    } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }

  if (loading || !user) return <Spinner />;

  return (
    <div className="min-h-screen">
      <header className="container flex h-16 items-center"><Logo /></header>
      <main id="main" className="container max-w-3xl pb-16">
        <ol className="mb-6 flex flex-wrap gap-2 text-xs" aria-label="Progress">
          {STEPS.map((s, i) => (
            <li key={s} aria-current={i === step ? "step" : undefined} className={cn("flex items-center gap-1.5 rounded-full border px-3 py-1", i === step && "border-primary bg-accent text-accent-foreground", i < step && "text-muted-foreground")}>
              {i < step ? <Check className="h-3 w-3" aria-hidden /> : <span>{i + 1}</span>}{s}
            </li>
          ))}
        </ol>
        {err && <Alert tone="error" className="mb-4">{err}</Alert>}

        {step === 0 && (
          <Card><CardHeader><CardTitle>Upload your resume</CardTitle><CardDescription>PDF or DOCX, up to 5 MB. This becomes the source of truth for everything we write on your behalf.</CardDescription></CardHeader>
            <CardContent>
              <label className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-10 text-center hover:bg-accent/40">
                <FileUp className="h-8 w-8 text-primary" aria-hidden />
                <span className="font-medium">{busy ? "Uploading…" : "Choose a file"}</span>
                <input type="file" className="sr-only" accept=".pdf,.docx" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
              </label>
            </CardContent></Card>
        )}
        {step === 1 && <Card><CardContent className="pt-5"><Spinner label="Reading your resume" /><p className="text-center text-sm text-muted-foreground">This usually takes a few seconds.</p></CardContent></Card>}
        {step === 2 && (
          <Card><CardHeader><CardTitle>Check what we extracted</CardTitle><CardDescription>Fix anything wrong or missing. Only what you confirm here will ever be used in your documents.</CardDescription></CardHeader>
            <CardContent className="space-y-6"><ProfileEditor value={profile} onChange={setProfile} />
              <div className="flex justify-end"><Button onClick={confirmProfile} loading={busy}>Confirm and continue</Button></div></CardContent></Card>
        )}
        {step === 3 && (
          <Card><CardHeader><CardTitle>Job preferences</CardTitle><CardDescription>Used to filter and score jobs. You can change these any time.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <Field label="Target job titles" htmlFor="pf-t" hint="Separate with commas, e.g. Data Engineer, Azure Data Engineer"><ListInput id="pf-t" value={prefs.target_titles} onChange={(v) => setPrefs({ ...prefs, target_titles: v })} /></Field>
              <Field label="Must-have skills" htmlFor="pf-s" hint="Separate with commas. Prefilled from your resume; remove any that are not essential."><ListInput id="pf-s" value={prefs.required_skills} onChange={(v) => setPrefs({ ...prefs, required_skills: v })} /></Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Countries" htmlFor="pf-c" hint="Country names or codes, e.g. India, Japan, US"><ListInput id="pf-c" value={prefs.countries} parse={(t) => parseCountries(t).codes} onChange={(v) => setPrefs({ ...prefs, countries: v })} /></Field>
                <Field label="Cities" htmlFor="pf-ci" hint="Separate with commas"><ListInput id="pf-ci" value={prefs.cities} onChange={(v) => setPrefs({ ...prefs, cities: v })} /></Field>
                <Field label="Minimum salary (per year)" htmlFor="pf-sa"><Input id="pf-sa" type="number" min={0} value={prefs.salary_min ?? ""} onChange={(e) => setPrefs({ ...prefs, salary_min: e.target.value ? Number(e.target.value) : null })} /></Field>
                <Field label="Currency" htmlFor="pf-cu"><Input id="pf-cu" maxLength={3} value={prefs.salary_currency} onChange={(e) => setPrefs({ ...prefs, salary_currency: e.target.value.toUpperCase() })} /></Field>
              </div>
              <fieldset className="flex flex-wrap gap-4"><legend className="mb-1 text-sm font-medium">Work mode</legend>
                {MODES.map((m) => <Checkbox key={m} label={m} checked={prefs.work_modes.includes(m)} onChange={(e) => setPrefs({ ...prefs, work_modes: e.target.checked ? [...prefs.work_modes, m] : prefs.work_modes.filter((x) => x !== m) })} />)}</fieldset>
              <Checkbox label="I need visa sponsorship" checked={prefs.needs_visa_sponsorship} onChange={(e) => setPrefs({ ...prefs, needs_visa_sponsorship: e.target.checked })} />
              <Checkbox label="I am open to relocating" checked={prefs.open_to_relocation} onChange={(e) => setPrefs({ ...prefs, open_to_relocation: e.target.checked })} />
              <div className="flex justify-between"><Button variant="ghost" onClick={() => setStep(2)}>Back</Button><Button onClick={() => savePrefs(4)} loading={busy}>Continue</Button></div>
            </CardContent></Card>
        )}
        {step === 4 && (
          <Card><CardHeader><CardTitle>Minimum match score</CardTitle><CardDescription>Only jobs scoring at or above this are saved to your matches. Higher means fewer, closer matches.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <div className="text-center text-5xl font-bold text-primary" aria-live="polite">{prefs.min_match_score}%</div>
              <input aria-label="Minimum match score" type="range" min={40} max={95} step={5} value={prefs.min_match_score} onChange={(e) => setPrefs({ ...prefs, min_match_score: Number(e.target.value) })} className="w-full accent-[hsl(var(--primary))]" />
              <p className="text-sm text-muted-foreground">70% is a good starting point. Free-plan matches are limited per month, so a higher threshold makes them count.</p>
              <div className="flex justify-between"><Button variant="ghost" onClick={() => setStep(3)}>Back</Button><Button onClick={() => savePrefs(5)} loading={busy}>Continue</Button></div>
            </CardContent></Card>
        )}
        {step === 5 && (
          <Card><CardHeader><CardTitle>Your consent</CardTitle><CardDescription>You decide what the platform may do. You can change these in Settings at any time.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <Checkbox checked={aiConsent} onChange={(e) => setAiConsent(e.target.checked)} label={<><strong>AI processing (required).</strong> Allow my resume and job descriptions to be processed by the configured AI provider to extract details, score jobs and draft documents.</>} />
              <Checkbox checked={autoApply} onChange={(e) => setAutoApply(e.target.checked)} label={<><strong>Automated applications (optional).</strong> Allow the platform to submit an application for me - but only after I approve that specific application. It never bypasses CAPTCHAs, logins or MFA.</>} />
              <div className="flex justify-between"><Button variant="ghost" onClick={() => setStep(4)}>Back</Button><Button onClick={finish} loading={busy}>Finish setup</Button></div>
            </CardContent></Card>
        )}
      </main>
    </div>
  );
}
