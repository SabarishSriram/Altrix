import { cn } from "cn";

/**
 * Altrix mark: a rising price line crossing above its moving average (the dotted line),
 * ending in a green signal dot. Inverts with the theme (tile = foreground colour).
 * src/app/icon.svg is the same drawing with fixed colours, for the browser tab.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-6 shrink-0", className)} aria-hidden>
      <rect width="32" height="32" rx="8" className="fill-foreground" />
      <path d="M7 22 L25 17" fill="none" strokeWidth="1.75" strokeLinecap="round" strokeDasharray="0.01 3.4" className="stroke-background/50" />
      <path
        d="M7 23 L12.5 16.5 L16.5 18 L24 10"
        fill="none"
        strokeWidth="2.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-background"
      />
      <circle cx="24" cy="10" r="2.75" className="fill-gain" />
    </svg>
  );
}
