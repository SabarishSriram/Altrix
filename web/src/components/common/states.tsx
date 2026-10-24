import { AlertTriangle, Inbox, RotateCw, ServerOff } from "lucide-react";
import { cn } from "cn";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";

export function ErrorState({
  error,
  onRetry,
  title,
  className,
}: {
  error: Error;
  onRetry?: () => void;
  title?: string;
  className?: string;
}) {
  const unreachable = error instanceof ApiError && error.unreachable;
  const Icon = unreachable ? ServerOff : AlertTriangle;
  return (
    <div
      role="alert"
      className={cn("flex flex-col items-center justify-center gap-3 rounded-lg border px-6 py-10 text-center", className)}
    >
      <Icon className="size-5 text-muted-foreground" aria-hidden />
      <div className="space-y-1">
        <p className="text-sm font-medium">{title ?? (unreachable ? "API unavailable" : "Could not load data")}</p>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">{error.message}</p>
        {unreachable && (
          <p className="mx-auto max-w-md pt-1 text-xs text-muted-foreground">
            Start it with <code className="rounded bg-muted px-1 py-0.5 font-mono">uvicorn api.main:app --port 8000</code>{" "}
            from the repository root.
          </p>
        )}
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RotateCw className="size-3.5" aria-hidden />
          Retry
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-10 text-center", className)}>
      <Inbox className="size-5 text-muted-foreground/70" aria-hidden />
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action}
    </div>
  );
}
