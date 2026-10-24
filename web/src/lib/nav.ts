import { FlaskConical, LayoutGrid, LineChart, ScanSearch, Settings, type LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/overview", label: "Overview", description: "Latest scan at a glance", icon: LayoutGrid },
  { href: "/scanner", label: "Stock Scanner", description: "NIFTY 100 · 20/50 SMA crossover signals on the latest trading day", icon: ScanSearch },
  { href: "/stocks", label: "Stock Analysis", description: "Price history, moving averages and crossover signals", icon: LineChart },
  { href: "/backtest", label: "Backtesting", description: "Historical simulation of the baseline strategy", icon: FlaskConical },
  { href: "/settings", label: "Settings", description: "Strategy, data source and API configuration", icon: Settings },
];

export function navItemFor(pathname: string): NavItem {
  return NAV_ITEMS.find((i) => pathname === i.href || pathname.startsWith(`${i.href}/`)) ?? NAV_ITEMS[0];
}
