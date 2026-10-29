"use server";

import { cookies } from "next/headers";

import { ACCESS_CODE, ACCESS_COOKIE, ACCESS_TOKEN } from "@/lib/access";

export type UnlockResult = { ok: true; next: string } | { ok: false };

/** Checks the code; on success sets the access cookie and says where to go (`next` if it is a same-site path). */
export async function unlock(code: string, next: string | null): Promise<UnlockResult> {
  if (code !== ACCESS_CODE) {
    await new Promise((r) => setTimeout(r, 600)); // slows down guessing
    return { ok: false };
  }
  (await cookies()).set(ACCESS_COOKIE, ACCESS_TOKEN, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    // no maxAge: a browser-session cookie, so the code is asked again after the browser closes
  });
  return { ok: true, next: next && next.startsWith("/") && !next.startsWith("//") ? next : "/overview" };
}
