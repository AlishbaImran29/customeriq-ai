import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// The gate in front of every page. A visitor who is not signed in sees the landing page (at /) or is sent to /login.
// It also renews the Supabase sign-in on each page request, so a long visit does not end suddenly.
// The API checks the token again on every call, so this is a convenience, not the protection.
// Demo mode (no backend configured) has nothing to sign in to.
export async function proxy(request: NextRequest) {
  if (!process.env.NEXT_PUBLIC_API_BASE_URL) return NextResponse.next();

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const { pathname, search } = request.nextUrl;
  const isPublic = pathname === "/login" || pathname === "/welcome";

  let response = NextResponse.next({ request });
  let signedIn = false;
  if (url && anon) {
    const supabase = createServerClient(url, anon, {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (list) => {
          list.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          list.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        },
      },
    });
    const { data } = await supabase.auth.getUser();
    signedIn = Boolean(data.user);
  }

  if (signedIn || isPublic) return response;

  // Visitors who open the bare address see the landing page; deeper links go to sign-in.
  if (pathname === "/") return NextResponse.redirect(new URL("/welcome", request.url));
  const login = new URL("/login", request.url);
  login.searchParams.set("next", pathname + search);
  return NextResponse.redirect(login);
}

export const config = {
  // Skip the API (so uploads are not buffered here), Next.js internals, and static files.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
