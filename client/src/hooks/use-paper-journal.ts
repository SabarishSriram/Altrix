"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { loadCloudJournal, mergeLocalIntoCloud, saveCloudJournal, type CloudJournal } from "@/lib/cloud-journal";
import { emptyJournal, journalIsPersistent, saveJournal, useJournal, type Journal } from "@/lib/paper-journal";
import { supabase } from "@/lib/supabase";

export type JournalMode = "local" | "cloud";

export interface PaperJournal {
  /** "cloud" when Supabase is configured (one shared journal, no sign-in), otherwise this browser's localStorage. */
  mode: JournalMode;
  /** null while the cloud journal is loading (or failed to load). */
  journal: Journal | null;
  save: (next: Journal) => Promise<boolean>;
  cloudError: string | null;
  reloadCloud: () => void;
  /** Trades saved in this browser, which can be moved into the cloud journal. */
  localTrades: number;
  migrateLocal: () => Promise<boolean>;
  persistent: boolean;
}

const message = (e: unknown) => (e instanceof Error ? e.message : typeof e === "object" && e && "message" in e ? String(e.message) : String(e));

export function usePaperJournal(): PaperJournal {
  const local = useJournal();
  const sb = supabase();
  const [cloud, setCloud] = useState<CloudJournal | null>(null);
  const [cloudError, setCloudError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const cloudRef = useRef(cloud);
  useEffect(() => {
    cloudRef.current = cloud;
  });

  // Load the journal, and again whenever the tab becomes visible (edits on another device).
  useEffect(() => {
    if (!sb) return;
    let live = true;
    const load = () =>
      loadCloudJournal(sb)
        .then((data) => {
          if (!live) return;
          setCloud(data);
          setCloudError(null);
        })
        .catch((e) => live && setCloudError(message(e)));
    void load();
    const onVisible = () => document.visibilityState === "visible" && void load();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      live = false;
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [sb, reloadKey]);

  const mode: JournalMode = sb ? "cloud" : "local";

  const save = useCallback(
    async (next: Journal): Promise<boolean> => {
      if (!sb) {
        saveJournal(next);
        return true;
      }
      const prev = cloudRef.current;
      if (!prev) return false;
      setCloud({ journal: next, hasSettings: true }); // optimistic
      try {
        await saveCloudJournal(sb, prev, next);
        return true;
      } catch (e) {
        toast.error("Couldn't save the journal", { description: `${message(e)}. The last saved journal was restored.` });
        setCloud(prev);
        setReloadKey((k) => k + 1);
        return false;
      }
    },
    [sb],
  );

  const migrateLocal = useCallback(async () => {
    const target = cloudRef.current;
    if (!sb || !target) return false;
    const merged = mergeLocalIntoCloud(target, local);
    if (!(await save(merged))) return false;
    // Only forget the browser copy once every local trade is confirmed in the database.
    try {
      const check = await loadCloudJournal(sb);
      const have = new Set(check.journal.trades.map((t) => t.id));
      if (!local.trades.every((t) => have.has(t.id))) throw new Error("some trades are missing after the upload");
      saveJournal(emptyJournal());
      setCloud(check);
      return true;
    } catch (e) {
      toast.error("Couldn't confirm the move", { description: `${message(e)}. The trades are still in this browser.` });
      return false;
    }
  }, [sb, local, save]);

  return {
    mode,
    journal: mode === "cloud" ? (cloud?.journal ?? null) : local,
    save,
    cloudError: mode === "cloud" ? cloudError : null,
    reloadCloud: () => setReloadKey((k) => k + 1),
    localTrades: local.trades.length,
    migrateLocal,
    persistent: journalIsPersistent(),
  };
}
