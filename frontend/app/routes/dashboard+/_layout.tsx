import type { LoaderFunctionArgs, TypedResponse } from '@remix-run/node'
import { Outlet, useLoaderData } from '@remix-run/react'
import { redirect } from '@remix-run/node' // Added json
import { getAuth } from '@clerk/remix/ssr.server' // Clerk's getAuth
import { ROUTE_PATH as ONBOARDING_USERNAME_PATH } from '#app/routes/onboarding+/username'
import { ROUTE_PATH as SIGN_IN_PATH } from '#app/routes/auth+/sign-in.$.tsx' // Assuming path, adjust if needed
import { Navigation } from '#app/components/navigation'
import { Header } from '#app/components/header'

export const ROUTE_PATH = '/dashboard' as const

export type LoaderData = Exclude<
  Awaited<ReturnType<typeof loader>>,
  Response | TypedResponse<unknown>
>

export const loader = async (args: LoaderFunctionArgs) => {
  const { request } = args;

  const { userId, sessionId } = await getAuth(args);

  if (!userId || !sessionId) {
    // If no active user/session, redirect to the sign-in page.
    const params = new URLSearchParams();
    params.set("redirect_url", new URL(request.url).pathname);
    return redirect(`${SIGN_IN_PATH}?${params.toString()}`);
  }

  // At this point, user is authenticated with Clerk.
  // We need to ensure this Clerk user is provisioned in our local DB
  // and has completed any app-specific onboarding (like username selection).

  // Fetch the local user profile using clerkUserId
  // The `clerkUser` object from `getAuth` (if `loadUser: true` in root.tsx) contains Clerk user details.
  // Its `id` property is the Clerk User ID.
  const localUser = clerkUser?.id ? await prisma.user.findUnique({
    where: { clerkUserId: clerkUser.id }, // Assuming your Prisma User model has `clerkUserId`
    include: {
      image: { select: { id: true } }, // Keep existing includes if relevant
      roles: { select: { name: true } },
    },
  }) : null;

  if (!localUser) {
    // This case should ideally be handled by webhooks creating the user.
    // If webhook hasn't processed yet, or if there's a mismatch:
    // Option 1: Redirect to a sync page or error.
    // Option 2: Try to create/link user here (can be complex, webhooks are better).
    // For now, if localUser is not found for an authenticated Clerk user,
    // it implies an issue with user provisioning via webhooks or data consistency.
    // Redirecting to sign-in might cause a loop if Clerk session is still active.
    // A specific error page or a re-sync mechanism might be better.
    // For this example, we'll throw an error or redirect to a safe page.
    // This could also be a redirect to an onboarding step if that's the flow.
    console.warn(`Clerk user ${clerkUser?.id} authenticated but no local user found. Redirecting to sign-in.`);
    const params = new URLSearchParams();
    params.set("error", "user_not_provisioned");
    return redirect(`${SIGN_IN_PATH}?${params.toString()}`); // Or a dedicated error/sync page
  }
  
  // Check for app-specific onboarding steps, like username
  if (!localUser.username) {
    return redirect(ONBOARDING_USERNAME_PATH);
  }

  const subscription = await prisma.subscription.findUnique({
    where: { userId: localUser.id }, // Use localUser.id for subscription query
  });

  // Return data including the localUser profile
  return json({
    user: localUser, // This is your application's User model instance
    clerkUser, // This is Clerk's user object, pass if needed by UI
    subscription,
  });
};

export default function Dashboard() {
  const { user, subscription } = useLoaderData<typeof loader>() // `user` is now localUser

  return (
    <div className="flex min-h-[100vh] w-full flex-col bg-secondary dark:bg-black">
      {/* Pass localUser to Navigation. Adjust Navigation component if it expects Clerk user object directly */}
      <Navigation user={user} planId={subscription?.planId} />
      <Header />
      <Outlet />
    </div>
  )
}
