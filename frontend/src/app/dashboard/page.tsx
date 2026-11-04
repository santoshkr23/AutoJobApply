"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Briefcase, CalendarCheck, Gift, Target } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge, ScoreBadge } from "@/components/ui/badge";
import { Alert, EmptyState, PageHeader, Spinner } from "@/components/ui/feedback";
import { api, errorMessage } from "@/lib/api";
import { formatDate, titleCase } from "@/lib/utils";

type Dash = {
  totals: { matches: number; applications: number; applied: number; interviews: number; offers: number; needs_action: number };
  applications_by_status: Record<string, number>; applications_per_day: { date: string; count: number }[];
  match_score_distribution: Record<string, number>; usage: Record<string, { limit: number; used: number; remaining: number }>;
  top_matches: { match_id: string; job_id: string; score: number; title: string; company: string }[];
  recent_applications: { id: string; status: string; title: string; company: string; updated_at: string }[];
};

const COLORS = ["hsl(var(--primary))", "hsl(var(--success))", "hsl(var(--warning))", "hsl(var(--muted-foreground))"];

export default function Overview() {
  const [d, setD] = useState<Dash | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api<Dash>("/dashboard").then(setD).catch((e) => setErr(errorMessage(e))); }, []);
  if (err) return <Alert tone="error">{err}</Alert>;
  if (!d) return <Spinner />;

  const stats = [
    { label: "Matched jobs", value: d.totals.matches, icon: Target },
    { label: "Applications", value: d.totals.applications, icon: Briefcase },
    { label: "Interviews", value: d.totals.interviews, icon: CalendarCheck },
    { label: "Offers", value: d.totals.offers, icon: Gift },
  ];
  const byStatus = Object.entries(d.applications_by_status).map(([k, v]) => ({ name: titleCase(k.toLowerCase()), value: v }));
  const dist = Object.entries(d.match_score_distribution).map(([k, v]) => ({ name: k, value: v }));
  const usage = d.usage.matched_jobs_per_month;

  return (
    <>
      <PageHeader title="Overview" description="Your job search at a glance." />
      {d.totals.needs_action > 0 && (
        <Alert tone="warning" className="mb-4" title={`${d.totals.needs_action} application(s) need your attention`}>
          <Link className="underline" href="/dashboard/applications?status=MANUAL_REQUIRED">Review manual steps</Link> · <Link className="underline" href="/dashboard/applications?status=PENDING_APPROVAL">Review pending approvals</Link>
        </Alert>
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label}><CardContent className="flex items-center justify-between p-5"><div><p className="text-sm text-muted-foreground">{s.label}</p><p className="text-3xl font-bold">{s.value}</p></div><s.icon className="h-8 w-8 text-primary/70" aria-hidden /></CardContent></Card>
        ))}
      </div>
      {usage && (
        <Card className="mt-4"><CardContent className="p-5"><div className="mb-2 flex justify-between text-sm"><span>Matched jobs this month</span><span className="text-muted-foreground">{usage.used} / {usage.limit}</span></div>
          <div className="h-2 rounded-full bg-muted" role="progressbar" aria-valuenow={usage.used} aria-valuemin={0} aria-valuemax={usage.limit}><div className="h-2 rounded-full bg-primary" style={{ width: `${usage.limit ? Math.min(100, (usage.used / usage.limit) * 100) : 100}%` }} /></div></CardContent></Card>
      )}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Applications by status</CardTitle></CardHeader><CardContent className="h-64">
          {byStatus.length === 0 ? <EmptyState title="No applications yet">Start one from a matched job.</EmptyState> : (
            <ResponsiveContainer width="100%" height="100%"><BarChart data={byStatus}><CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" /><XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} height={55} textAnchor="end" /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="value" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>)}
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Match score distribution</CardTitle></CardHeader><CardContent className="h-64">
          {dist.every((x) => x.value === 0) ? <EmptyState title="No matches yet">Run matching from the Matched jobs page.</EmptyState> : (
            <ResponsiveContainer width="100%" height="100%"><BarChart data={dist}><CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="value" radius={[4, 4, 0, 0]}>{dist.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar></BarChart></ResponsiveContainer>)}
        </CardContent></Card>
        <Card className="lg:col-span-2"><CardHeader><CardTitle>Applications created (last 30 days)</CardTitle></CardHeader><CardContent className="h-56">
          {d.applications_per_day.length === 0 ? <EmptyState title="No activity yet" /> : (
            <ResponsiveContainer width="100%" height="100%"><LineChart data={d.applications_per_day}><CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" /><XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} tick={{ fontSize: 11 }} /><Tooltip /><Line type="monotone" dataKey="count" stroke="hsl(var(--primary))" strokeWidth={2} dot /></LineChart></ResponsiveContainer>)}
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Top new matches</CardTitle></CardHeader><CardContent>
          {d.top_matches.length === 0 ? <p className="text-sm text-muted-foreground">Nothing yet.</p> : <ul className="divide-y">{d.top_matches.map((m) => (
            <li key={m.match_id} className="flex items-center justify-between gap-3 py-2 text-sm"><span><Link className="font-medium hover:underline" href="/dashboard/matches">{m.title}</Link><br /><span className="text-muted-foreground">{m.company}</span></span><ScoreBadge score={m.score} /></li>))}</ul>}
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Recent applications</CardTitle></CardHeader><CardContent>
          {d.recent_applications.length === 0 ? <p className="text-sm text-muted-foreground">Nothing yet.</p> : <ul className="divide-y">{d.recent_applications.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 py-2 text-sm"><span><Link className="font-medium hover:underline" href={`/dashboard/applications/${a.id}`}>{a.title}</Link><br /><span className="text-muted-foreground">{a.company} · {formatDate(a.updated_at)}</span></span><StatusBadge status={a.status} /></li>))}</ul>}
        </CardContent></Card>
      </div>
    </>
  );
}
