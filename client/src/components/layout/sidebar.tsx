"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "cn";

import { LogoMark } from "@/components/brand/logo-mark";
import { DataStatus } from "@/components/layout/data-status";
import { useScanner } from "@/components/providers/scanner-provider";
import { NAV_ITEMS, navItemFor } from "@/lib/nav";

export function Wordmark({ className }: { className?: string }) {
  return (
    <Link href="/overview" className={cn("flex items-center gap-2 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50", className)}>
      <LogoMark />
      <span className="text-[15px] font-semibold tracking-tight">Altrix</span>
    </Link>
  );
}

export function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const active = navItemFor(pathname).href;
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const isActive = href === active;
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/50",
              isActive ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function SidebarFooter() {
  const { health } = useScanner();
  return (
    <div className="space-y-2 border-t px-4 py-3">
      <DataStatus />
      <p className="text-[11px] text-muted-foreground">
        Altrix{health.data ? ` v${health.data.version}` : ""} · Research only
      </p>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-svh w-56 shrink-0 flex-col border-r bg-sidebar lg:flex">
      <div className="flex h-14 items-center px-4">
        <Wordmark />
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-2">
        <NavLinks />
      </div>
      <SidebarFooter />
    </aside>
  );
}
