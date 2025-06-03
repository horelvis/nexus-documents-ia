import { authMiddleware, redirectToSignIn } from "@clerk/nextjs";
import { NextResponse } from "next/server";

export default authMiddleware({
  // Routes that can be accessed while signed out
  publicRoutes: [
    "/",
    "/auth/login",
    "/auth/register",
    "/pricing",
    "/api/webhooks/clerk",
    "/api/webhooks/stripe"
  ],
  // Routes that can always be accessed, and have
  // no authentication information
  ignoredRoutes: [
    "/api/webhooks/clerk",
    "/api/webhooks/stripe"
  ],
  afterAuth(auth, req, evt) {
    // Handle users who aren't authenticated
    if (!auth.userId && !auth.isPublicRoute) {
      return redirectToSignIn({ returnBackUrl: req.url });
    }

    // Redirect signed in users from auth pages to dashboard
    if (auth.userId && (req.nextUrl.pathname === "/auth/login" || req.nextUrl.pathname === "/auth/register")) {
      return NextResponse.redirect(new URL('/dashboard', req.url));
    }

    // Allow users to access the requested page
    return NextResponse.next();
  }
});

export const config = {
  // Protects all routes, including api/trpc.
  // See https://clerk.com/docs/references/nextjs/auth-middleware
  // for more information about configuring your Middleware
  matcher: ["/((?!.+\\.[\\w]+$|_next).*)", "/", "/(api|trpc)(.*)"],
};