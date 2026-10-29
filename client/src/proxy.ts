import { NextResponse, type NextRequest } from "next/server";

import { ACCESS_COOKIE, ACCESS_TOKEN } from "@/lib/access";

// Every page needs the access cookie; without it the visitor lands on /unlock and comes back afterwards.
export function proxy(request: NextRequest) {
  if (request.cookies.get(ACCESS_COOKIE)?.value === ACCESS_TOKEN) return NextResponse.next();
  const url = new URL("/unlock", request.url);
  const back = request.nextUrl.pathname + request.nextUrl.search;
  if (back !== "/") url.searchParams.set("next", back);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!unlock|_next/static|_next/image|favicon.ico|icon.svg|.*\\.(?:png|jpg|jpeg|svg|webp|ico|txt)$).*)"],
};
