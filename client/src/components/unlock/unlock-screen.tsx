"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { cn } from "cn";

import { unlock } from "@/app/unlock/actions";
import { LogoMark } from "@/components/brand/logo-mark";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import { NAV_ITEMS } from "@/lib/nav";
import { markTabUnlocked } from "@/lib/unlock-session";

const LENGTH = 4;
type Status = "idle" | "checking" | "error" | "success";

const FEATURES = NAV_ITEMS.filter((i) => ["/scanner", "/smart-money", "/backtest", "/investments"].includes(i.href));

// ---- illustration: made-up daily candles whose EMA 20 crosses above EMA 50 -----------------------

const W = 480;
const H = 170;

interface Candle {
  o: number;
  h: number;
  l: number;
  c: number;
}

const CANDLES: Candle[] = (() => {
  let seed = 11;
  const rand = () => ((seed = (seed * 16807) % 2147483647), seed / 2147483647 - 0.5);
  const out: Candle[] = [];
  let p = 100;
  for (let i = 0; i < 56; i++) {
    const o = p;
    const c = o + (i < 24 ? -0.45 : 0.75) + rand() * 3.4;
    out.push({ o, c, h: Math.max(o, c) + Math.abs(rand()) * 1.6, l: Math.min(o, c) - Math.abs(rand()) * 1.6 });
    p = c;
  }
  return out;
})();
const ema = (xs: number[], n: number) => {
  const k = 2 / (n + 1);
  const out: number[] = [];
  xs.forEach((x, i) => out.push(i ? x * k + out[i - 1] * (1 - k) : x));
  return out;
};
const CLOSES = CANDLES.map((c) => c.c);
const FAST = ema(CLOSES, 20);
const SLOW = ema(CLOSES, 50);
const LO = Math.min(...CANDLES.map((c) => c.l));
const HI = Math.max(...CANDLES.map((c) => c.h));
const STEP = W / CANDLES.length;
const px = (i: number) => (i + 0.5) * STEP;
const py = (v: number) => H - 8 - ((v - LO) / (HI - LO)) * (H - 16);
const line = (xs: number[]) => xs.map((v, i) => `${i ? "L" : "M"}${px(i).toFixed(1)} ${py(v).toFixed(1)}`).join(" ");
const CROSS = FAST.findIndex((f, i) => i > 10 && f > SLOW[i] && FAST[i - 1] <= SLOW[i - 1]);

function CrossoverPreview() {
  const body = STEP * 0.62;
  return (
    <figure className="rounded-lg border bg-card">
      <figcaption className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div>
          <p className="text-sm font-semibold">EMA 20 / 50 crossover</p>
          <p className="text-xs text-muted-foreground">Illustration · daily candles</p>
        </div>
        <span className="rounded-sm bg-gain-soft px-1.5 py-px text-[11px] font-semibold text-gain">BUY</span>
      </figcaption>
      <div className="px-4 pt-4 pb-3">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" aria-hidden>
          {[0.25, 0.5, 0.75].map((f) => (
            <line key={f} x1="0" x2={W} y1={H * f} y2={H * f} stroke="var(--border)" strokeWidth="1" />
          ))}
          {CROSS > 0 && <line x1={px(CROSS)} x2={px(CROSS)} y1="0" y2={H} stroke="var(--gain)" strokeWidth="1" strokeDasharray="3 3" opacity="0.7" />}
          {CANDLES.map((c, i) => {
            const color = c.c >= c.o ? "var(--gain)" : "var(--loss)";
            const top = py(Math.max(c.o, c.c));
            return (
              <g key={i}>
                <line x1={px(i)} x2={px(i)} y1={py(c.h)} y2={py(c.l)} stroke={color} strokeWidth="1" />
                <rect x={px(i) - body / 2} y={top} width={body} height={Math.max(1, py(Math.min(c.o, c.c)) - top)} rx="0.75" fill={color} />
              </g>
            );
          })}
          <path d={line(SLOW)} fill="none" stroke="var(--muted-foreground)" strokeWidth="1.5" strokeDasharray="2 3" strokeLinecap="round" />
          <path d={line(FAST)} fill="none" stroke="var(--foreground)" strokeWidth="1.5" strokeOpacity="0.75" strokeLinejoin="round" />
          {CROSS > 0 && <circle cx={px(CROSS)} cy={py(FAST[CROSS])} r="4.5" fill="var(--gain)" stroke="var(--card)" strokeWidth="2" />}
        </svg>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-1.5 rounded-[1px] bg-gain" />Up day</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-1.5 rounded-[1px] bg-loss" />Down day</span>
          <span className="flex items-center gap-1.5"><span className="h-0.5 w-3 rounded-full bg-foreground/75" />EMA 20</span>
          <span className="flex items-center gap-1.5"><span className="h-0 w-3 border-t-2 border-dotted border-muted-foreground" />EMA 50</span>
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-gain" />Signal</span>
        </div>
      </div>
    </figure>
  );
}

// ---- page -------------------------------------------------------------------------------------

export function UnlockScreen() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [focused, setFocused] = useState(false);
  const busy = status === "checking" || status === "success";

  const submit = async (value: string) => {
    if (value.length !== LENGTH || busy) return;
    setStatus("checking");
    const next = new URLSearchParams(window.location.search).get("next");
    const result = await unlock(value, next);
    if (result.ok) {
      setStatus("success");
      markTabUnlocked();
      router.replace(result.next);
    } else {
      setStatus("error");
      setCode("");
      input.current?.focus();
    }
  };

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (busy) return;
    const value = e.target.value.replace(/\D/g, "").slice(0, LENGTH);
    setCode(value);
    if (status === "error") setStatus("idle");
    if (value.length === LENGTH) void submit(value);
  };

  const active = focused && !busy ? Math.min(code.length, LENGTH - 1) : -1;

  return (
    <div className="flex min-h-svh flex-col lg:grid lg:grid-cols-2">
      {/* code side: first on small screens, right column on large ones */}
      <main className="relative isolate flex min-h-svh flex-col overflow-hidden px-4 py-6 sm:px-8 lg:order-2 lg:py-8">
        {/* faint dot grid, fading out towards the edges */}
        <div
          aria-hidden
          className="absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_at_center,black_25%,transparent_75%)]"
          style={{ backgroundImage: "radial-gradient(var(--border) 1px, transparent 1px)", backgroundSize: "20px 20px" }}
        />
        <div className="flex justify-end">
          <ThemeToggle />
        </div>

        <div className="flex flex-1 items-center justify-center py-8">
          <form
            className="w-full max-w-[420px] rounded-xl border bg-card shadow-sm"
            onSubmit={(e) => {
              e.preventDefault();
              void submit(code);
            }}
          >
            <div className="px-6 py-8 sm:px-8 sm:py-10">
              <div className="flex flex-col items-center text-center">
                <LogoMark className="size-12" />
                <p className="mt-3 text-lg font-semibold tracking-tight">Altrix</p>
                <h1 className="mt-6 text-xl font-semibold tracking-tight sm:text-2xl">Enter access code</h1>
                <p className="mt-1 text-[13px] text-muted-foreground">Type the 4-digit code to open your dashboard.</p>
              </div>

              <div className="relative mt-7">
                <div className="grid grid-cols-4 gap-2 sm:gap-3">
                  {Array.from({ length: LENGTH }, (_, i) => (
                    <div
                      key={i}
                      className={cn(
                        "flex aspect-square items-center justify-center rounded-lg border-[1.5px] bg-background transition-[border-color,box-shadow]",
                        status === "error"
                          ? "border-loss ring-3 ring-loss/15"
                          : status === "success"
                            ? "border-gain ring-3 ring-gain/15"
                            : i === active
                              ? "border-foreground/70 ring-3 ring-ring/30"
                              : i < code.length
                                ? "border-foreground/45"
                                : "border-foreground/25",
                      )}
                    >
                      {i < code.length || status === "success" ? (
                        <span className={cn("size-3 rounded-full", status === "success" ? "bg-gain" : "bg-foreground")} />
                      ) : i === active ? (
                        <span className="h-7 w-px animate-pulse bg-foreground" aria-hidden />
                      ) : null}
                    </div>
                  ))}
                </div>
                <input
                  ref={input}
                  value={code}
                  onChange={onChange}
                  onFocus={() => setFocused(true)}
                  onBlur={() => setFocused(false)}
                  autoFocus
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]*"
                  maxLength={LENGTH}
                  aria-label="Access code"
                  aria-invalid={status === "error"}
                  aria-describedby="unlock-status"
                  className="absolute inset-0 w-full cursor-text text-transparent caret-transparent opacity-0 outline-none"
                />
              </div>

              <p
                id="unlock-status"
                role={status === "error" ? "alert" : undefined}
                className={cn(
                  "mt-3 h-4 text-center text-xs",
                  status === "error" ? "text-loss" : status === "success" ? "text-gain" : "text-muted-foreground",
                )}
              >
                {status === "error" ? "That code isn't right. Try again." : status === "success" ? "Unlocked" : status === "checking" ? "Checking…" : ""}
              </p>

              <Button type="submit" size="lg" className="mt-4 h-10 w-full" disabled={code.length !== LENGTH || busy}>
                {status === "success" ? "Opening dashboard…" : status === "checking" ? "Checking…" : "Continue"}
                {status === "idle" || status === "error" ? <ArrowRight aria-hidden /> : null}
              </Button>
            </div>
          </form>
        </div>
      </main>

      {/* product side: below the form on small screens, left column on large ones */}
      <aside className="flex flex-col justify-center border-t bg-surface px-4 py-10 sm:px-8 lg:order-1 lg:border-t-0 lg:border-r lg:px-10 xl:px-16">
        <div className="mx-auto w-full max-w-md space-y-8">
          <div className="space-y-2">
            <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">NIFTY 100 signals, from the day&apos;s close.</h2>
            <p className="text-[13px] leading-relaxed text-muted-foreground">
              Scan for EMA crossovers and institutional footprints, test the strategy on ten years of history, and practise it
              with pretend money.
            </p>
          </div>
          <CrossoverPreview />
          <ul className="grid gap-4 sm:grid-cols-2 sm:gap-x-6">
            {FEATURES.map(({ href, label, description, icon: Icon }) => (
              <li key={href} className="flex gap-2.5">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-md border bg-card">
                  <Icon className="size-3.5" aria-hidden />
                </span>
                <div className="min-w-0">
                  <p className="text-[13px] font-medium">{label}</p>
                  <p className="line-clamp-2 text-xs text-muted-foreground">{description}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
