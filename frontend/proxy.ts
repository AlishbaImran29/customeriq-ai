import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// A quick gate: visitors without a sign-in cookie are sent to /login. This only
// checks that a cookie exists; the backend decides whether it is still valid
// (an expired one ends up at /login?reason=expired). Runs only for page requests.
const SESSION_COOKIE = "ciq_session";

export function proxy(request: NextRequest) {
  // Demo mode (no backend configured): there is nothing to sign in to.
  if (!process.env.NEXT_PUBLIC_API_BASE_URL) return NextResponse.next();

  const { pathname, search } = request.nextUrl;
  if (pathname === "/login" || request.cookies.has(SESSION_COOKIE)) return NextResponse.next();

  const url = new URL("/login", request.url);
  if (pathname !== "/") url.searchParams.set("next", pathname + search);
  return NextResponse.redirect(url);
}

export const config = {
  // Skip the API (so uploads are not buffered here), Next.js internals, and static files.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
