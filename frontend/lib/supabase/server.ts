import "server-only";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { SUPABASE_ANON_KEY, SUPABASE_URL } from "@/lib/supabase/env";

/** A Supabase client for Server Components: it reads the visitor's sign-in from their cookies. */
export async function supabaseServer() {
  const store = await cookies();
  return createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll: () => store.getAll(),
      setAll: (list) => {
        // Server Components cannot set cookies; the proxy (proxy.ts) renews the session on every page request instead.
        try {
          list.forEach(({ name, value, options }) => store.set(name, value, options));
        } catch {
          /* ignored on purpose */
        }
      },
    },
  });
}

/** The visitor's sign-in token for calls from the server to the API; null when signed out. */
export async function serverAccessToken(): Promise<string | null> {
  const supabase = await supabaseServer();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
