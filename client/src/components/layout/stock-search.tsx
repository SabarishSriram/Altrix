"use client";

import { useRouter } from "next/navigation";
import { useId, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import { cn } from "cn";

import { useScanner } from "@/components/providers/scanner-provider";
import { SignalBadge } from "@/components/stocks/signal-badge";
import { displaySymbol } from "@/lib/format";
import { stockHref } from "@/lib/routes";

const MAX_RESULTS = 8;

/** Jump to a stock's analysis page by symbol or company name (from the scanned universe). */
export function StockSearch({ className }: { className?: string }) {
  const router = useRouter();
  const { scanner } = useScanner();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const results = useMemo(() => {
    const q = query.trim().toUpperCase();
    if (!q || !scanner.data) return [];
    return scanner.data.stocks
      .filter((s) => s.symbol.includes(q) || (s.name ?? "").toUpperCase().includes(q))
      .sort((a, b) => Number(!a.symbol.startsWith(q)) - Number(!b.symbol.startsWith(q)) || a.symbol.localeCompare(b.symbol))
      .slice(0, MAX_RESULTS);
  }, [query, scanner.data]);

  const go = (symbol: string) => {
    setQuery("");
    setOpen(false);
    inputRef.current?.blur();
    router.push(stockHref(symbol));
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[active]) {
      e.preventDefault();
      go(results[active].symbol);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  };

  const showList = open && query.trim().length > 0;
  return (
    <div className={cn("relative", className)}>
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <input
        ref={inputRef}
        type="search"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && results[active] ? `${listId}-${active}` : undefined}
        aria-label="Search stocks"
        placeholder={scanner.data ? "Search NIFTY 100…" : "Loading stocks…"}
        disabled={!scanner.data}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
        className="h-8 w-full rounded-md border bg-background pr-2 pl-8 text-[13px] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 disabled:opacity-60"
      />
      {showList && (
        <ul
          id={listId}
          role="listbox"
          className="absolute top-full right-0 left-0 z-50 mt-1 max-h-80 overflow-y-auto rounded-md border bg-popover p-1 shadow-md"
        >
          {results.length === 0 ? (
            <li className="px-2 py-3 text-center text-xs text-muted-foreground">No matching stock</li>
          ) : (
            results.map((s, i) => (
              <li
                key={s.symbol}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => {
                  e.preventDefault();
                  go(s.symbol);
                }}
                onMouseEnter={() => setActive(i)}
                className={cn(
                  "flex cursor-pointer items-center justify-between gap-3 rounded-sm px-2 py-1.5",
                  i === active && "bg-muted",
                )}
              >
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium">{displaySymbol(s.symbol)}</span>
                  <span className="block truncate text-xs text-muted-foreground">{s.name}</span>
                </span>
                {s.signal !== "HOLD" && <SignalBadge signal={s.signal} />}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
