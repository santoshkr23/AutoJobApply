import type { Metadata } from "next";

export const metadata: Metadata = { title: "Privacy policy" };

export default function Privacy() {
  return (
    <article className="container max-w-3xl space-y-4 py-14">
      <h1 className="text-3xl font-bold">Privacy policy</h1>
      <p className="text-sm text-muted-foreground">Template text - have it reviewed by a qualified professional and adapted to your jurisdiction before launch.</p>
      <h2 className="text-xl font-semibold">What we collect</h2>
      <p>Account details, the resume you upload and the profile derived from it, your job preferences, application history, consents and billing records from our payment providers. We never store card numbers.</p>
      <h2 className="text-xl font-semibold">How we use it</h2>
      <p>To find and score jobs, prepare documents you approve, submit applications you authorize, send notifications you enable and operate your subscription. Resume text is sent to the configured AI provider only to perform these tasks.</p>
      <h2 className="text-xl font-semibold">Storage and security</h2>
      <p>Files are stored privately and shared only through short-lived signed links. Sensitive fields are encrypted. Access is limited to your account, and administrative actions are logged.</p>
      <h2 className="text-xl font-semibold">Your choices</h2>
      <p>You can withdraw consent, export your application data and delete your account at any time from Settings. Deleting your account removes your personal data; payment records are retained as the law requires.</p>
    </article>
  );
}
