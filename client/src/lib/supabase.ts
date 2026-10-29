// Supabase client for the cloud-synced paper journal (client/supabase/schema.sql).
//
// Nobody signs in: the publishable key (sb_publishable_..., or a legacy anon key) reads and writes the one
// shared journal, and the access-code page (src/proxy.ts) is the only gate. Without both variables the
// journal stays in this browser only. Never put the secret / service_role key in the frontend.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const cloudConfigured = Boolean(URL && ANON_KEY);

let client: SupabaseClient | null | undefined;

/** The browser's Supabase client, or null when cloud sync is not configured (or during prerendering). */
export function supabase(): SupabaseClient | null {
  if (client === undefined) {
    client =
      cloudConfigured && typeof window !== "undefined"
        ? createClient(URL!, ANON_KEY!, {
            auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
          })
        : null;
  }
  return client;
}
