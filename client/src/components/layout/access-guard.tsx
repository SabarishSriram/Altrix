"use client";

import { useEffect } from "react";

import { useTabUnlocked } from "@/lib/unlock-session";

/** Sends a tab that hasn't entered the access code to /unlock, then back here. */
export function AccessGuard({ children }: { children: React.ReactNode }) {
  const unlocked = useTabUnlocked();

  useEffect(() => {
    if (unlocked !== false) return;
    const back = window.location.pathname + window.location.search;
    window.location.replace(back === "/" ? "/unlock" : `/unlock?next=${encodeURIComponent(back)}`);
  }, [unlocked]);

  // Always rendered (Next.js validates every segment), but hidden until this tab is known to be unlocked.
  return <div hidden={unlocked !== true}>{children}</div>;
}
