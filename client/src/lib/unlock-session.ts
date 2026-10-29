// Per-tab half of the access gate: the proxy checks the (browser-session) cookie, and this flag in
// sessionStorage makes every new tab ask for the code again. A reload of an unlocked tab keeps it.

import { useSyncExternalStore } from "react";

const KEY = "altrix.unlocked";

export function markTabUnlocked(): void {
  try {
    window.sessionStorage.setItem(KEY, "1");
  } catch {
    // storage blocked: the cookie alone guards the site
  }
}

function read(): boolean {
  try {
    return window.sessionStorage.getItem(KEY) === "1";
  } catch {
    return true; // storage blocked: don't lock the visitor out for good
  }
}

const noSubscribe = () => () => {};

/** Whether this tab entered the code; null while prerendering and hydrating (not known yet). */
export function useTabUnlocked(): boolean | null {
  return useSyncExternalStore<boolean | null>(noSubscribe, read, () => null);
}
