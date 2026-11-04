"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Activity, CreditCard, LayoutDashboard, LifeBuoy, ListChecks, LogOut, ScrollText, SlidersHorizontal, Users } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/feedback";
import { adminApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/admin", label: "Overview", icon: LayoutDashboard }, { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/plans", label: "Plans and limits", icon: ListChecks }, { href: "/admin/sources", label: "Job sources", icon: Activity },
  { href: "/admin/payments", label: "Payments", icon: CreditCard }, { href: "/admin/logs", label: "Logs", icon: ScrollText },
  { href: "/admin/support", label: "Support", icon: LifeBuoy }, { href: "/admin/settings", label: "System", icon: SlidersHorizontal },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [admin, setAdmin] = useState<{ email: string; role: string } | null>(null);
  useEffect(() => { adminApi("/me").then(setAdmin).catch(() => router.replace("/admin/login")); }, [router]);
  if (!admin) return <Spinner />;
  return (
    <div className="min-h-screen md:grid md:grid-cols-[220px_1fr]">
      <aside className="border-b p-4 md:border-b-0 md:border-r">
        <p className="mb-4 font-semibold">Admin</p>
        <nav aria-label="Admin" className="flex gap-1 overflow-x-auto md:flex-col">{NAV.map((n) => {
          const active = n.href === "/admin" ? path === n.href : path.startsWith(n.href);
          return <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined} className={cn("flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm", active ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-muted")}><n.icon className="h-4 w-4" aria-hidden />{n.label}</Link>;
        })}</nav>
      </aside>
      <div className="min-w-0">
        <header className="flex h-14 items-center justify-end gap-2 border-b px-4"><span className="mr-auto text-sm text-muted-foreground">{admin.email} · {admin.role}</span><ThemeToggle />
          <Button variant="ghost" size="sm" onClick={async () => { await adminApi("/logout", { method: "POST" }); router.push("/admin/login"); }}><LogOut className="h-4 w-4" />Sign out</Button></header>
        <main id="main" className="p-4 md:p-8">{children}</main>
      </div>
    </div>
  );
}
