"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Textarea } from "@/components/ui/form";

export type Experience = { id?: string; company: string; title: string; location?: string | null; start_date?: string | null; end_date?: string | null; is_current: boolean; bullets: string[] };
export type Education = { institution: string; degree?: string | null; field?: string | null; start_date?: string | null; end_date?: string | null };
export type Certification = { name: string; issuer?: string | null; date?: string | null };
export type ProfileData = {
  full_name?: string | null; email?: string | null; phone?: string | null; location?: string | null; country?: string | null;
  headline?: string | null; summary?: string | null; skills: string[]; experience: Experience[]; education: Education[];
  certifications: Certification[]; projects: any[]; links: string[]; total_experience_years?: number | null;
};

export const emptyProfile = (): ProfileData => ({ skills: [], experience: [], education: [], certifications: [], projects: [], links: [] });

const lines = (v: string) => v.split("\n").map((s) => s.trim()).filter(Boolean);

export function ProfileEditor({ value, onChange }: { value: ProfileData; onChange: (v: ProfileData) => void }) {
  const set = <K extends keyof ProfileData>(k: K, v: ProfileData[K]) => onChange({ ...value, [k]: v });
  const setExp = (i: number, patch: Partial<Experience>) => set("experience", value.experience.map((e, j) => (j === i ? { ...e, ...patch } : e)));
  const setEdu = (i: number, patch: Partial<Education>) => set("education", value.education.map((e, j) => (j === i ? { ...e, ...patch } : e)));
  const setCert = (i: number, patch: Partial<Certification>) => set("certifications", value.certifications.map((e, j) => (j === i ? { ...e, ...patch } : e)));

  return (
    <div className="space-y-8">
      <section className="grid gap-4 sm:grid-cols-2" aria-label="Basic details">
        <Field label="Full name" htmlFor="p-name"><Input id="p-name" value={value.full_name ?? ""} onChange={(e) => set("full_name", e.target.value)} /></Field>
        <Field label="Email" htmlFor="p-email"><Input id="p-email" type="email" value={value.email ?? ""} onChange={(e) => set("email", e.target.value)} /></Field>
        <Field label="Phone" htmlFor="p-phone" hint="Stored encrypted."><Input id="p-phone" value={value.phone ?? ""} onChange={(e) => set("phone", e.target.value)} /></Field>
        <Field label="Location" htmlFor="p-loc"><Input id="p-loc" value={value.location ?? ""} onChange={(e) => set("location", e.target.value)} placeholder="City, Country" /></Field>
        <Field label="Country code" htmlFor="p-country" hint="Two letters, e.g. IN, US, GB."><Input id="p-country" maxLength={2} value={value.country ?? ""} onChange={(e) => set("country", e.target.value.toUpperCase())} /></Field>
        <Field label="Headline" htmlFor="p-head"><Input id="p-head" value={value.headline ?? ""} onChange={(e) => set("headline", e.target.value)} /></Field>
        <div className="sm:col-span-2"><Field label="Summary" htmlFor="p-sum"><Textarea id="p-sum" value={value.summary ?? ""} onChange={(e) => set("summary", e.target.value)} rows={4} /></Field></div>
        <div className="sm:col-span-2"><Field label="Skills" htmlFor="p-skills" hint="Comma separated. Only list skills you genuinely have - AI tailoring never adds to this list.">
          <Textarea id="p-skills" rows={3} value={value.skills.join(", ")} onChange={(e) => set("skills", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} /></Field></div>
      </section>

      <section aria-label="Experience" className="space-y-3">
        <div className="flex items-center justify-between"><h3 className="font-semibold">Experience</h3>
          <Button type="button" variant="outline" size="sm" onClick={() => set("experience", [...value.experience, { company: "", title: "", is_current: false, bullets: [] }])}><Plus className="h-3.5 w-3.5" />Add role</Button></div>
        {value.experience.map((e, i) => (
          <div key={e.id ?? i} className="space-y-3 rounded-lg border p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Company" htmlFor={`e-co-${i}`}><Input id={`e-co-${i}`} value={e.company} onChange={(ev) => setExp(i, { company: ev.target.value })} /></Field>
              <Field label="Job title" htmlFor={`e-ti-${i}`}><Input id={`e-ti-${i}`} value={e.title} onChange={(ev) => setExp(i, { title: ev.target.value })} /></Field>
              <Field label="Start" htmlFor={`e-st-${i}`} hint="e.g. Jan 2021"><Input id={`e-st-${i}`} value={e.start_date ?? ""} onChange={(ev) => setExp(i, { start_date: ev.target.value })} /></Field>
              <Field label="End" htmlFor={`e-en-${i}`}><Input id={`e-en-${i}`} value={e.end_date ?? ""} disabled={e.is_current} onChange={(ev) => setExp(i, { end_date: ev.target.value })} /></Field>
            </div>
            <Checkbox label="I currently work here" checked={e.is_current} onChange={(ev) => setExp(i, { is_current: ev.target.checked, end_date: ev.target.checked ? null : e.end_date })} />
            <Field label="Achievements (one per line)" htmlFor={`e-bu-${i}`}><Textarea id={`e-bu-${i}`} rows={4} value={e.bullets.join("\n")} onChange={(ev) => setExp(i, { bullets: ev.target.value.split("\n") })} onBlur={(ev) => setExp(i, { bullets: lines(ev.target.value) })} /></Field>
            <Button type="button" variant="ghost" size="sm" onClick={() => set("experience", value.experience.filter((_, j) => j !== i))}><Trash2 className="h-3.5 w-3.5" />Remove role</Button>
          </div>
        ))}
      </section>

      <section aria-label="Education" className="space-y-3">
        <div className="flex items-center justify-between"><h3 className="font-semibold">Education</h3>
          <Button type="button" variant="outline" size="sm" onClick={() => set("education", [...value.education, { institution: "" }])}><Plus className="h-3.5 w-3.5" />Add</Button></div>
        {value.education.map((e, i) => (
          <div key={i} className="grid gap-3 rounded-lg border p-4 sm:grid-cols-2">
            <Field label="Institution" htmlFor={`ed-in-${i}`}><Input id={`ed-in-${i}`} value={e.institution} onChange={(ev) => setEdu(i, { institution: ev.target.value })} /></Field>
            <Field label="Degree" htmlFor={`ed-de-${i}`}><Input id={`ed-de-${i}`} value={e.degree ?? ""} onChange={(ev) => setEdu(i, { degree: ev.target.value })} /></Field>
            <Field label="Field" htmlFor={`ed-fi-${i}`}><Input id={`ed-fi-${i}`} value={e.field ?? ""} onChange={(ev) => setEdu(i, { field: ev.target.value })} /></Field>
            <Field label="End year" htmlFor={`ed-en-${i}`}><Input id={`ed-en-${i}`} value={e.end_date ?? ""} onChange={(ev) => setEdu(i, { end_date: ev.target.value })} /></Field>
            <Button type="button" variant="ghost" size="sm" className="w-fit" onClick={() => set("education", value.education.filter((_, j) => j !== i))}><Trash2 className="h-3.5 w-3.5" />Remove</Button>
          </div>
        ))}
      </section>

      <section aria-label="Certifications" className="space-y-3">
        <div className="flex items-center justify-between"><h3 className="font-semibold">Certifications</h3>
          <Button type="button" variant="outline" size="sm" onClick={() => set("certifications", [...value.certifications, { name: "" }])}><Plus className="h-3.5 w-3.5" />Add</Button></div>
        {value.certifications.map((c, i) => (
          <div key={i} className="grid gap-3 rounded-lg border p-4 sm:grid-cols-3">
            <Field label="Name" htmlFor={`c-na-${i}`}><Input id={`c-na-${i}`} value={c.name} onChange={(ev) => setCert(i, { name: ev.target.value })} /></Field>
            <Field label="Issuer" htmlFor={`c-is-${i}`}><Input id={`c-is-${i}`} value={c.issuer ?? ""} onChange={(ev) => setCert(i, { issuer: ev.target.value })} /></Field>
            <Field label="Date" htmlFor={`c-da-${i}`}><Input id={`c-da-${i}`} value={c.date ?? ""} onChange={(ev) => setCert(i, { date: ev.target.value })} /></Field>
            <Button type="button" variant="ghost" size="sm" className="w-fit" onClick={() => set("certifications", value.certifications.filter((_, j) => j !== i))}><Trash2 className="h-3.5 w-3.5" />Remove</Button>
          </div>
        ))}
      </section>
    </div>
  );
}

/** Drop empty rows and tidy values before sending to the API. */
export function cleanProfile(p: ProfileData): ProfileData {
  const n = (s?: string | null) => (s && s.trim() ? s.trim() : null);
  return {
    ...p,
    full_name: n(p.full_name), email: n(p.email), phone: n(p.phone), location: n(p.location), country: n(p.country),
    headline: n(p.headline), summary: n(p.summary),
    experience: p.experience.filter((e) => e.company.trim() && e.title.trim()).map((e) => ({ ...e, bullets: e.bullets.map((b) => b.trim()).filter(Boolean), start_date: n(e.start_date), end_date: e.is_current ? null : n(e.end_date) })),
    education: p.education.filter((e) => e.institution.trim()),
    certifications: p.certifications.filter((c) => c.name.trim()),
  };
}
