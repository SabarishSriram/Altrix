"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { useResource, type Resource } from "@/hooks/use-resource";
import { api, errorMessage } from "@/lib/api";
import type { HealthResponse, RefreshStatus, ScannerResponse } from "@/lib/types";

const HEALTH_INTERVAL_MS = 60_000;
const JOB_POLL_MS = 3_000;

type RefreshKind = "rescan" | "download";

interface ScannerContextValue {
  scanner: Resource<ScannerResponse>;
  health: Resource<HealthResponse>;
  refreshing: RefreshKind | null;
  rescan: () => Promise<void>;
  downloadLatest: () => Promise<void>;
}

const ScannerContext = createContext<ScannerContextValue | null>(null);

/** One scanner result and API status shared by every dashboard page. */
export function ScannerProvider({ children }: { children: React.ReactNode }) {
  const scanner = useResource("scanner", api.scanner);
  const health = useResource("health", api.health);
  const [rescanning, setRescanning] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const reloadHealth = health.reload;
  useEffect(() => {
    const id = setInterval(() => void reloadHealth(), HEALTH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [reloadHealth]);

  const finishDownload = useCallback(
    async (status: RefreshStatus) => {
      if (status.state === "succeeded") {
        const failed = status.failed.length;
        (failed ? toast.warning : toast.success)("Market data updated", {
          description: `${status.message ?? ""}${failed ? `. Failed: ${status.failed.map((f) => f.symbol).join(", ")}` : ""}`,
        });
      } else {
        toast.error("Download failed", { description: status.message ?? "The stored data is unchanged." });
      }
      await Promise.all([scanner.reload(), health.reload()]);
    },
    [scanner, health],
  );
  const finishRef = useRef(finishDownload);
  useEffect(() => {
    finishRef.current = finishDownload;
  });

  // Track a download started here, or one already running when the page loaded.
  const jobRunning = health.data?.refresh.state === "running" && health.data.refresh.kind === "download";
  const tracking = downloading || jobRunning;
  useEffect(() => {
    if (!tracking) return;
    let done = false;
    const id = setInterval(async () => {
      if (done) return;
      try {
        const status = await api.refreshStatus();
        if (status.state === "running" || done) return;
        done = true;
        clearInterval(id);
        setDownloading(false);
        await finishRef.current(status);
      } catch (e) {
        done = true;
        clearInterval(id);
        setDownloading(false);
        toast.error("Lost contact with the API", { description: errorMessage(e) });
      }
    }, JOB_POLL_MS);
    return () => {
      done = true;
      clearInterval(id);
    };
  }, [tracking]);

  const rescan = useCallback(async () => {
    setRescanning(true);
    try {
      await api.refresh(false);
      await Promise.all([scanner.reload(), health.reload()]);
      toast.success("Rescan complete", { description: "Signals recomputed from the stored data." });
    } catch (e) {
      toast.error("Rescan failed", { description: errorMessage(e) });
    } finally {
      setRescanning(false);
    }
  }, [scanner, health]);

  const downloadLatest = useCallback(async () => {
    try {
      await api.refresh(true); // 202 started, or 409 already running: track it either way
      setDownloading(true);
      toast.info("Downloading new daily bars", { description: "Fetching only bars newer than the stored data." });
    } catch (e) {
      toast.error("Could not start the download", { description: errorMessage(e) });
    }
  }, []);

  const refreshing: RefreshKind | null = tracking ? "download" : rescanning ? "rescan" : null;
  const value = useMemo(
    () => ({ scanner, health, refreshing, rescan, downloadLatest }),
    [scanner, health, refreshing, rescan, downloadLatest],
  );
  return <ScannerContext.Provider value={value}>{children}</ScannerContext.Provider>;
}

export function useScanner(): ScannerContextValue {
  const ctx = useContext(ScannerContext);
  if (!ctx) throw new Error("useScanner must be used inside <ScannerProvider>");
  return ctx;
}
