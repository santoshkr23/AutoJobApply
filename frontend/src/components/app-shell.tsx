"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Bell, Briefcase, CreditCard, FileText, LayoutDashboard, LogOut, Menu, Search, Settings, Target, User as UserIcon, X } from "lucide-react";
import { Logo } from "@/components/public-shell";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/feedback";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/dashboard/jobs", label: "Job discovery", icon: Search },
  { href: "/dashboard/matches", label: "Matched jobs", icon: Target },
  { href: "/dashboard/applications", label: "Applications", icon: Briefcase },
  { href: "/dashboard/resumes", label: "Resumes", icon: FileText },
  { href: "/dashboard/profile", label: "Profile", icon: UserIcon },
  { href: "/dashboard/subscription", label: "Subscription", icon: CreditCard },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (loading) return;
    if (!user) window.location.href = `/login?next=${encodeURIComponent(path)}`;
    else if (!user.onboarding_completed) window.location.href = "/onboarding";
  }, [loading, user, path]);

  useEffect(() => {
    if (!user) return;
    const load = () => api("/notifications?limit=1").then((d) => setUnread(d.unread)).catch(() => undefined);
    void load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [user, path]);

  useEffect(() => setOpen(false), [path]);

  if (loading || !user || !user.onboarding_completed) return <Spinner />;

  const nav = (
    <nav aria-label="Dashboard" className="flex flex-col gap-1">
      {NAV.map((n) => {
        const active = n.href === "/dashboard" ? path === n.href : path.startsWith(n.href);
        return (
          <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
            className={cn("flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium", active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
            <n.icon className="h-4 w-4" aria-hidden />{n.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="hidden border-r p-4 lg:flex lg:flex-col lg:gap-6"><Logo />{nav}
        <p className="mt-auto rounded-md bg-muted p-3 text-xs text-muted-foreground">Plan: <strong className="text-foreground">{user.plan}</strong></p></aside>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <div className="relative h-full w-64 space-y-6 bg-background p-4"><div className="flex items-center justify-between"><Logo /><Button variant="ghost" size="icon" aria-label="Close menu" onClick={() => setOpen(false)}><X className="h-4 w-4" /></Button></div>{nav}</div>
        </div>
      )}
      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b bg-background/90 px-4 backdrop-blur">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}><Menu className="h-4 w-4" /></Button>
          <span className="hidden truncate text-sm text-muted-foreground sm:block">{user.full_name || user.email}</span>
          <div className="ml-auto flex items-center gap-1">
            <Link href="/dashboard/notifications" className="relative inline-flex h-9 w-9 items-center justify-center rounded-md hover:bg-accent" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}>
              <Bell className="h-4 w-4" />{unread > 0 && <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] text-destructive-foreground">{unread > 9 ? "9+" : unread}</span>}
            </Link>
            <ThemeToggle />
            <Button variant="ghost" size="sm" onClick={logout}><LogOut className="h-4 w-4" />Sign out</Button>
          </div>
        </header>
        <main id="main" className="flex-1 p-4 md:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
