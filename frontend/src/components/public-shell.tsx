import Link from "next/link";
import { Briefcase } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/features", label: "Features" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/pricing", label: "Pricing" },
  { href: "/faq", label: "FAQ" },
];

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 font-semibold">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground"><Briefcase className="h-4 w-4" aria-hidden /></span>
      AutoJobApply
    </Link>
  );
}

export function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
        <div className="container flex h-16 items-center justify-between gap-4">
          <Logo />
          <nav aria-label="Main" className="hidden items-center gap-6 text-sm md:flex">
            {NAV.map((n) => <Link key={n.href} href={n.href} className="text-muted-foreground hover:text-foreground">{n.label}</Link>)}
          </nav>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Link href="/login" className={cn(buttonVariants({ variant: "ghost" }), "hidden sm:inline-flex")}>Sign in</Link>
            <Link href="/register" className={buttonVariants()}>Get started</Link>
          </div>
        </div>
        <nav aria-label="Mobile" className="container flex gap-4 overflow-x-auto pb-2 text-sm md:hidden">
          {NAV.map((n) => <Link key={n.href} href={n.href} className="whitespace-nowrap text-muted-foreground">{n.label}</Link>)}
        </nav>
      </header>
      <main id="main" className="flex-1">{children}</main>
      <footer className="border-t py-10 text-sm text-muted-foreground">
        <div className="container flex flex-col justify-between gap-6 md:flex-row">
          <div className="max-w-sm space-y-2">
            <Logo />
            <p>An AI job-search assistant. You approve every application. We never bypass CAPTCHAs, logins or site rules.</p>
          </div>
          <div className="flex gap-12">
            <div className="space-y-2"><p className="font-medium text-foreground">Product</p>{NAV.map((n) => <Link key={n.href} className="block hover:text-foreground" href={n.href}>{n.label}</Link>)}</div>
            <div className="space-y-2"><p className="font-medium text-foreground">Company</p>
              <Link className="block hover:text-foreground" href="/contact">Contact</Link>
              <Link className="block hover:text-foreground" href="/privacy">Privacy</Link>
              <Link className="block hover:text-foreground" href="/terms">Terms</Link></div>
          </div>
        </div>
      </footer>
    </div>
  );
}
