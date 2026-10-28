"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { toast } from "sonner";

import { loadCloudJournal, mergeLocalIntoCloud, saveCloudJournal, type CloudJournal } from "@/lib/cloud-journal";
import { emptyJournal, journalIsPersistent, saveJournal, useJournal, type Journal } from "@/lib/paper-journal";
import { cloudConfigured, supabase } from "@/lib/supabase";

export type JournalMode = "local" | "cloud";

export interface PaperJournal {
  /** "cloud" when signed in to Supabase, otherwise this browser's localStorage. */
  mode: JournalMode;
  /** null while the cloud journal is loading (or failed to load). */
  journal: Journal | null;
  save: (next: Journal) => Promise<boolean>;
  cloudConfigured: boolean;
  authReady: boolean;
  email: string | null;
  cloudError: string | null;
  reloadCloud: () => void;
  sendLink: (email: string) => Promise<boolean>;
  verifyCode: (email: string, code: string) => Promise<boolean>;
  signOut: () => Promise<void>;
  /** Trades saved in this browser, which can be moved into the signed-in account. */
  localTrades: number;
  migrateLocal: () => Promise<boolean>;
  persistent: boolean;
}

const message = (e: unknown) => (e instanceof Error ? e.message : typeof e === "object" && e && "message" in e ? String(e.message) : String(e));

export function usePaperJournal(): PaperJournal {
  const local = useJournal();
  const sb = supabase();
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(!cloudConfigured);
  const [cloud, setCloud] = useState<{ userId: string; data: CloudJournal } | null>(null);
  const [cloudError, setCloudError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const cloudRef = useRef(cloud);
  useEffect(() => {
    cloudRef.current = cloud;
  });

  // Session: restored from storage, picked up from a magic-link redirect, refreshed, or ended.
  useEffect(() => {
    if (!sb) return;
    const { data } = sb.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      setAuthReady(true);
      if (!s) setCloud(null);
    });
    return () => data.subscription.unsubscribe();
  }, [sb]);

  const userId = session?.user.id ?? null;

  // Load the signed-in user's journal, and again whenever the tab becomes visible (edits on another device).
  useEffect(() => {
    if (!sb || !userId) return;
    let live = true;
    const load = () =>
      loadCloudJournal(sb)
        .then((data) => {
          if (!live) return;
          setCloud({ userId, data });
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
  }, [sb, userId, reloadKey]);

  const mode: JournalMode = sb && userId ? "cloud" : "local";
  const current = cloud && cloud.userId === userId ? cloud : null;

  const save = useCallback(
    async (next: Journal): Promise<boolean> => {
      if (!sb || !userId) {
        saveJournal(next);
        return true;
      }
      const prev = cloudRef.current;
      if (!prev || prev.userId !== userId) return false;
      setCloud({ userId, data: { journal: next, hasSettings: true } }); // optimistic
      try {
        await saveCloudJournal(sb, userId, prev.data, next);
        return true;
      } catch (e) {
        toast.error("Couldn't save to your account", { description: `${message(e)}. Your last saved journal was restored.` });
        setCloud(prev);
        setReloadKey((k) => k + 1);
        return false;
      }
    },
    [sb, userId],
  );

  const sendLink = useCallback(
    async (email: string) => {
      if (!sb) return false;
      const { error } = await sb.auth.signInWithOtp({
        email,
        options: { emailRedirectTo: `${window.location.origin}/investments`, shouldCreateUser: true },
      });
      if (error) toast.error("Couldn't send the sign-in email", { description: error.message });
      return !error;
    },
    [sb],
  );

  const verifyCode = useCallback(
    async (email: string, code: string) => {
      if (!sb) return false;
      const { error } = await sb.auth.verifyOtp({ email, token: code, type: "email" });
      if (error) toast.error("That code didn't work", { description: error.message });
      return !error;
    },
    [sb],
  );

  const signOut = useCallback(async () => {
    await sb?.auth.signOut();
  }, [sb]);

  const migrateLocal = useCallback(async () => {
    const target = cloudRef.current;
    if (!sb || !userId || !target || target.userId !== userId) return false;
    const merged = mergeLocalIntoCloud(target.data, local);
    if (!(await save(merged))) return false;
    // Only forget the browser copy once every local trade is confirmed in the database.
    try {
      const check = await loadCloudJournal(sb);
      const have = new Set(check.journal.trades.map((t) => t.id));
      if (!local.trades.every((t) => have.has(t.id))) throw new Error("some trades are missing after the upload");
      saveJournal(emptyJournal());
      setCloud({ userId, data: check });
      return true;
    } catch (e) {
      toast.error("Couldn't confirm the move", { description: `${message(e)}. The trades are still in this browser.` });
      return false;
    }
  }, [sb, userId, local, save]);

  return {
    mode,
    journal: mode === "cloud" ? (current?.data.journal ?? null) : local,
    save,
    cloudConfigured,
    authReady,
    email: session?.user.email ?? null,
    cloudError: mode === "cloud" ? cloudError : null,
    reloadCloud: () => setReloadKey((k) => k + 1),
    sendLink,
    verifyCode,
    signOut,
    localTrades: local.trades.length,
    migrateLocal,
    persistent: journalIsPersistent(),
  };
}
