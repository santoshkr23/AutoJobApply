import type { Metadata } from "next";

export const metadata: Metadata = { title: "FAQ" };

const FAQ = [
  ["Will the AI invent skills or experience?", "No. Tailoring may reorder and rephrase your own bullets. Every generated line is checked in code: new numbers, skills you do not list, or altered dates and employers are rejected and the original text is used instead. The change log shows what happened."],
  ["Will you apply without asking me?", "Never. Automated submission needs the 'automated applications' consent in Settings and your approval on each application, and it is limited to paid plans."],
  ["What about CAPTCHAs and logins?", "We do not bypass them. If a site shows a CAPTCHA, asks you to sign in or sends a verification code, the application is marked 'manual required' and you finish it yourself."],
  ["How do you find jobs?", "Only through official APIs, employer-published boards and feeds that allow it. We do not scrape sites that forbid it."],
  ["How do I know an application really went through?", "We mark it Applied only when the employer site shows a confirmation. If we cannot confirm, it stays 'manual required' so you can check."],
  ["Can I delete my data?", "Yes. Settings > Delete account removes your personal data. Payment records are kept as required by law, detached from your identity."],
  ["What does it cost?", "Free (10 matched jobs a month), Pro INR 499 a month and Premium INR 999 a month. Limits are listed on the pricing page; none are 'unlimited'."],
] as const;

export default function Faq() {
  return (
    <div className="container max-w-3xl py-14">
      <h1 className="text-3xl font-bold">Frequently asked questions</h1>
      <div className="mt-6 divide-y rounded-lg border">
        {FAQ.map(([q, a]) => (
          <details key={q} className="group p-4"><summary className="cursor-pointer font-medium">{q}</summary><p className="mt-2 text-muted-foreground">{a}</p></details>
        ))}
      </div>
    </div>
  );
}
