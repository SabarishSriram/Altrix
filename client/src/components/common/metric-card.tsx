import { cn } from "cn";

import { Skeleton } from "@/components/ui/skeleton";

export function MetricCard({
  label,
  value,
  hint,
  tone = "default",
  loading,
  className,
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  hint?: React.ReactNode;
  tone?: "default" | "gain" | "loss" | "muted";
  loading?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5 rounded-lg border bg-card px-4 py-3.5", className)}>
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        {tone === "gain" && <span className="size-1.5 rounded-full bg-gain" aria-hidden />}
        {tone === "loss" && <span className="size-1.5 rounded-full bg-loss" aria-hidden />}
        {label}
      </div>
      {loading ? (
        <Skeleton className="h-7 w-20" />
      ) : (
        <div
          className={cn(
            "num truncate text-2xl font-semibold tracking-tight",
            tone === "gain" && "text-gain",
            tone === "loss" && "text-loss",
            tone === "muted" && "text-muted-foreground",
          )}
        >
          {value}
        </div>
      )}
      {hint && <div className="truncate text-xs text-muted-foreground">{loading ? <Skeleton className="h-3 w-28" /> : hint}</div>}
    </div>
  );
}
