import type { Metadata } from "next";

export const metadata: Metadata = { title: "Terms of service" };

export default function Terms() {
  return (
    <article className="container max-w-3xl space-y-4 py-14">
      <h1 className="text-3xl font-bold">Terms of service</h1>
      <p className="text-sm text-muted-foreground">Template text - have it reviewed by a qualified professional before launch.</p>
      <h2 className="text-xl font-semibold">The service</h2>
      <p>AutoJobApply helps you discover jobs, prepare application materials and, where supported and authorized by you, submit applications. We do not guarantee interviews, offers or that any submission will be accepted by an employer.</p>
      <h2 className="text-xl font-semibold">Your responsibilities</h2>
      <p>You are responsible for the accuracy of your profile and for reviewing every document before approving it, and for following the rules of the employers and platforms you apply to.</p>
      <h2 className="text-xl font-semibold">Automation limits</h2>
      <p>Automated submission is limited to supported sites. We do not bypass CAPTCHAs, authentication or access controls; those steps are always left to you.</p>
      <h2 className="text-xl font-semibold">Subscriptions</h2>
      <p>Paid plans renew monthly until cancelled. Cancellation takes effect at the end of the paid period. Plan limits are published on the pricing page.</p>
    </article>
  );
}
