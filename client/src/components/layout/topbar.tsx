"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";
import { ChevronDown, CloudDownload, Menu, RefreshCw, RotateCw } from "lucide-react";
import { cn } from "cn";

import { DataStatus } from "@/components/layout/data-status";
import { NavLinks, SidebarFooter, Wordmark } from "@/components/layout/sidebar";
import { StockSearch } from "@/components/layout/stock-search";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { useScanner } from "@/components/providers/scanner-provider";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, formatRelative } from "@/lib/format";
import { navItemFor } from "@/lib/nav";

function MobileNav() {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="lg:hidden" aria-label="Open navigation">
          <Menu className="size-4" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="flex w-64 flex-col gap-0 p-0">
        <SheetHeader className="h-14 justify-center px-4">
          <SheetTitle asChild>
            <div>
              <Wordmark />
            </div>
          </SheetTitle>
          <SheetDescription className="sr-only">Main navigation</SheetDescription>
        </SheetHeader>
        <div className="flex-1 px-2 py-2">
          <NavLinks onNavigate={() => setOpen(false)} />
        </div>
        <SidebarFooter />
      </SheetContent>
    </Sheet>
  );
}

function RefreshMenu() {
  const { refreshing, rescan, downloadLatest, scanner, health } = useScanner();
  const busy = refreshing !== null;
  // Read-only deployments (e.g. Vercel) get new data by redeploying, so the API rejects downloads.
  const canDownload = health.data?.downloads_enabled !== false;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={busy} aria-label="Refresh data">
          <RefreshCw className={cn("size-3.5", busy && "animate-spin")} aria-hidden />
          <span className="hidden sm:inline">
            {refreshing === "download" ? "Downloading…" : refreshing === "rescan" ? "Rescanning…" : "Refresh"}
          </span>
          <ChevronDown className="size-3 text-muted-foreground" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          {scanner.data ? `Scanned ${formatRelative(scanner.data.scanned_at)}` : "Not scanned yet"}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void rescan()} className="items-start gap-2.5 py-2">
          <RotateCw className="mt-0.5 size-4" aria-hidden />
          <div>
            <div className="text-[13px] font-medium">Rescan stored data</div>
            <div className="text-xs text-muted-foreground">Recompute signals from the data already on disk.</div>
          </div>
        </DropdownMenuItem>
        {canDownload && (
          <DropdownMenuItem onSelect={() => void downloadLatest()} className="items-start gap-2.5 py-2">
            <CloudDownload className="mt-0.5 size-4" aria-hidden />
            <div>
              <div className="text-[13px] font-medium">Download new bars</div>
              <div className="text-xs text-muted-foreground">
                Fetch only end-of-day bars newer than the stored data from Yahoo Finance, then rescan. About a minute.
              </div>
            </div>
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Topbar() {
  const pathname = usePathname();
  const item = navItemFor(pathname);
  const { scanner } = useScanner();

  return (
    <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur-sm supports-backdrop-filter:bg-background/80">
      <div className="flex h-14 items-center gap-3 px-4 sm:px-6">
        <MobileNav />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[15px] font-semibold tracking-tight">{item.label}</h1>
          <p className="hidden truncate text-xs text-muted-foreground md:block">{item.description}</p>
        </div>
        <StockSearch className="hidden w-56 md:block xl:w-72" />
        <div className="hidden flex-col items-end leading-tight sm:flex">
          <span className="text-[11px] text-muted-foreground">Data as of</span>
          {scanner.data ? (
            <span className="num text-[13px] font-medium">{formatDate(scanner.data.data_as_of)}</span>
          ) : (
            <Skeleton className="mt-0.5 h-4 w-20" />
          )}
        </div>
        <ThemeToggle />
        <RefreshMenu />
      </div>
      <div className="flex h-8 items-center gap-3 border-t bg-surface px-4 text-[11px] text-muted-foreground sm:px-6">
        <span className="font-medium text-foreground/80">Historical daily data — not real-time</span>
        <span className="hidden sm:inline" aria-hidden>·</span>
        <span className="hidden truncate sm:inline">End-of-day prices. Signals use the day&apos;s close and are research only, not advice.</span>
        <div className="ml-auto flex items-center gap-3">
          <span className="num sm:hidden">{scanner.data ? formatDate(scanner.data.data_as_of) : ""}</span>
          <DataStatus compact />
        </div>
      </div>
      <div className="border-t px-4 py-2 md:hidden">
        <StockSearch />
      </div>
    </header>
  );
}
