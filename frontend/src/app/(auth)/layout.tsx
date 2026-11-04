import Link from "next/link";
import { Logo } from "@/components/public-shell";
import { ThemeToggle } from "@/components/theme-toggle";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="container flex h-16 items-center justify-between"><Logo /><ThemeToggle /></header>
      <main id="main" className="flex flex-1 items-start justify-center px-4 pb-16 pt-6 sm:items-center">
        <div className="w-full max-w-md rounded-xl border bg-card p-6 shadow-sm sm:p-8">{children}</div>
      </main>
      <footer className="pb-6 text-center text-xs text-muted-foreground"><Link href="/privacy" className="hover:underline">Privacy</Link> · <Link href="/terms" className="hover:underline">Terms</Link></footer>
    </div>
  );
}
