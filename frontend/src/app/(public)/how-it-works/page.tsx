import type { Metadata } from "next";

export const metadata: Metadata = { title: "How it works" };

const STEPS = [
  ["Upload your resume", "PDF or DOCX. We extract your details and show them to you."],
  ["Verify and set preferences", "Correct anything the parser got wrong, choose roles, locations, salary and your minimum match score."],
  ["Review matches", "See each job's score, the skills you have and the ones you lack, and an honest explanation."],
  ["Prepare documents", "Generate a tailored resume and cover letter. Review the change log, edit, and approve."],
  ["Approve and apply", "Give explicit approval. On supported sites we submit and verify the confirmation; elsewhere we send you to the job link."],
  ["Track the outcome", "Move applications through interview and offer. Export your history any time."],
] as const;

export default function HowItWorks() {
  return (
    <div className="container max-w-3xl py-14">
      <h1 className="text-3xl font-bold">How it works</h1>
      <ol className="mt-8 space-y-6">
        {STEPS.map(([t, d], i) => (
          <li key={t} className="flex gap-4">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary font-semibold text-primary-foreground">{i + 1}</span>
            <div><h2 className="font-semibold">{t}</h2><p className="text-muted-foreground">{d}</p></div>
          </li>
        ))}
      </ol>
    </div>
  );
}
