import type { Metadata } from "next";

export const metadata: Metadata = { title: "Features" };

const GROUPS = [
  ["Job discovery", ["Official APIs and employer job boards (Greenhouse, Lever), plus generic JSON feeds", "Duplicate detection and automatic expiry of closed postings", "Search with country, work mode, salary, category and freshness filters", "Per-source health monitoring for administrators"]],
  ["AI matching", ["Weighted 0-100 score with configurable weights", "Matched and missing skills, experience, location, salary and visa fit", "Related-but-different skills are noted, never counted as a match", "Your minimum score decides what reaches your inbox"]],
  ["Resume and cover letter", ["PDF and DOCX output for every application", "Full change log of what was reworded or reordered", "Facts, dates, employers and certifications always copied from your verified profile", "Edit anything before you approve"]],
  ["Application tracking and automation", ["Twelve clear statuses from Matched to Offer", "Consent-gated automated submission on supported sites only", "CAPTCHA, login or MFA hands the application back to you", "Retries with backoff and a full event history"]],
  ["Export and insight", ["CSV and Excel export of every application", "Dashboard charts for status, activity and match quality", "Email and in-app notifications you control"]],
] as const;

export default function Features() {
  return (
    <div className="container max-w-4xl py-14">
      <h1 className="text-3xl font-bold">Features</h1>
      <p className="mt-2 text-muted-foreground">Everything is designed so the AI helps without ever inventing your history or acting behind your back.</p>
      <div className="mt-8 space-y-8">
        {GROUPS.map(([title, items]) => (
          <section key={title}><h2 className="text-xl font-semibold">{title}</h2>
            <ul className="mt-3 list-disc space-y-1.5 pl-6 text-muted-foreground">{items.map((i) => <li key={i}>{i}</li>)}</ul></section>
        ))}
      </div>
    </div>
  );
}
