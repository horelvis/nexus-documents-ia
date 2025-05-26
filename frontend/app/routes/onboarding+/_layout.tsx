import type { LoaderFunctionArgs } from '@remix-run/node'
import { Outlet } from '@remix-run/react'
import { redirect, json } from '@remix-run/node'
import { requireUser } from '#app/modules/auth/auth.server'
import { prisma } from '#app/utils/db.server'
import { getDomainPathname } from '#app/utils/misc.server'
import { PLANS } from '#app/modules/stripe/plans'
import { ROUTE_PATH as DASHBOARD_PATH } from '#app/routes/dashboard+/_layout'
import { ROUTE_PATH as ONBOARDING_USERNAME_PATH } from '#app/routes/onboarding+/username'
import { ROUTE_PATH as ONBOARDING_PLAN_PATH } from '#app/routes/onboarding+/plan' // Actual import
import { Logo } from '#app/components/logo'

export const ROUTE_PATH = '/onboarding' as const

export async function loader({ request }: LoaderFunctionArgs) {
  const user = await requireUser(request)
  const pathname = getDomainPathname(request)

  const subscription = await prisma.subscription.findUnique({
    where: { userId: user.id },
  })

  // Definition of "onboarding complete":
  // User has a subscription record, AND
  // (it's a non-free plan OR its status is 'active' - covering active free plans too)
  const onboardingComplete =
    subscription && (subscription.planId !== PLANS.FREE || subscription.status === 'active')

  if (onboardingComplete) {
    if (
      pathname === ROUTE_PATH ||
      pathname === ONBOARDING_USERNAME_PATH ||
      pathname === ONBOARDING_PLAN_PATH
    ) {
      return redirect(DASHBOARD_PATH)
    }
  } else {
    // Onboarding is not complete
    if (pathname === ROUTE_PATH) {
      if (!user.username) return redirect(ONBOARDING_USERNAME_PATH)
      return redirect(ONBOARDING_PLAN_PATH) // Has username, but onboarding not complete
    }

    if (pathname === ONBOARDING_USERNAME_PATH) {
      if (user.username) {
        // Has username, but onboarding not complete (e.g. subscription missing/not active)
        return redirect(ONBOARDING_PLAN_PATH)
      }
      // If no username, they are on the correct page.
    }

    if (pathname === ONBOARDING_PLAN_PATH) {
      if (!user.username) {
        return redirect(ONBOARDING_USERNAME_PATH) // Must set username first
      }
      // If has username and on plan page, but onboarding not complete, they are on the correct page.
    }
  }

  return json({}) // No redirection needed, user is on an appropriate page or outside onboarding.
}

export default function Onboarding() {
  return (
    <div className="relative flex h-screen w-full bg-card">
      <div className="absolute left-1/2 top-8 mx-auto -translate-x-1/2 transform justify-center">
        <Logo />
      </div>
      <div className="z-10 h-screen w-screen">
        <Outlet />
      </div>
      <div className="base-grid fixed h-screen w-screen opacity-40" />
      <div className="fixed bottom-0 h-screen w-screen bg-gradient-to-t from-[hsl(var(--card))] to-transparent" />
    </div>
  )
}
