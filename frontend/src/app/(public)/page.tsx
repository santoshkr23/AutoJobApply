import Link from "next/link";
import { CheckCircle2, FileText, Search, ShieldCheck, Target, UserCheck } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const FEATURES = [
  { icon: Search, title: "Jobs from authorized sources", text: "Discovery runs only through official APIs, employer boards and feeds that permit it. No unauthorized scraping." },
  { icon: Target, title: "Explainable match scores", text: "Every job gets a 0-100 score with matched and missing skills, experience, location and salary fit - and why." },
  { icon: FileText, title: "Honest tailored resumes", text: "AI re-orders and rephrases what you already did. A code-level check rejects any skill, number or date you did not provide." },
  { icon: UserCheck, title: "You stay in control", text: "Documents and every submission need your explicit approval. CAPTCHA, login or MFA? We stop and hand it to you." },
  { icon: ShieldCheck, title: "Privacy by design", text: "Private encrypted storage, per-user isolation, audit logs, consent records and one-click account deletion." },
  { icon: CheckCircle2, title: "Truthful tracking", text: "An application is only marked Applied when the site confirms it - never on a guess." },
];

export default function Home() {
  return (
    <>
      <section className="container py-16 text-center md:py-24">
        <p className="mx-auto mb-4 w-fit rounded-full bg-accent px-3 py-1 text-xs font-medium text-accent-foreground">AI career agent with a human in the loop</p>
        <h1 className="mx-auto max-w-3xl text-4xl font-bold tracking-tight md:text-6xl">Find the right jobs. Apply with confidence.</h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-muted-foreground">Upload your resume once. AutoJobApply finds matching roles, explains the fit, prepares tailored documents from your real experience, and submits only what you approve.</p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link href="/register" className={cn(buttonVariants({ size: "lg" }))}>Start free</Link>
          <Link href="/how-it-works" className={cn(buttonVariants({ size: "lg", variant: "outline" }))}>See how it works</Link>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">Free plan: 10 matched jobs a month. No credit card.</p>
      </section>
      <section className="container pb-20">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <Card key={f.title}>
              <CardHeader><f.icon className="h-6 w-6 text-primary" aria-hidden /><CardTitle className="pt-2">{f.title}</CardTitle></CardHeader>
              <CardContent className="text-sm text-muted-foreground">{f.text}</CardContent>
            </Card>
          ))}
        </div>
      </section>
    </>
  );
}
