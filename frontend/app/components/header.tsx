import { useLocation } from '@remix-run/react'
import { ROUTE_PATH as DASHBOARD_PATH } from '#app/routes/dashboard+/_layout'
import { ROUTE_PATH as BILLING_PATH } from '#app/routes/dashboard+/settings.billing'
import { ROUTE_PATH as SETTINGS_PATH } from '#app/routes/dashboard+/settings'
import { ROUTE_PATH as ADMIN_PATH } from '#app/routes/admin+/_layout'
import { Link } from "@remix-run/react";
import { useUser, UserButton } from "@clerk/remix";

export function Header() {
  const { isSignedIn, user } = useUser(); // Clerk's useUser hook
  const location = useLocation()
  const allowedLocations = [DASHBOARD_PATH, BILLING_PATH, SETTINGS_PATH, ADMIN_PATH]

  const headerTitle = () => {
    if (location.pathname === DASHBOARD_PATH) return 'Dashboard'
    if (location.pathname === BILLING_PATH) return 'Billing'
    if (location.pathname === SETTINGS_PATH) return 'Settings'
    if (location.pathname === ADMIN_PATH) return 'Admin'
  }
  const headerDescription = () => {
    if (location.pathname === DASHBOARD_PATH)
      return 'Manage your Apps and view your usage.'
    if (location.pathname === SETTINGS_PATH) return 'Manage your account settings.'
    if (location.pathname === BILLING_PATH)
      return 'Manage billing and your subscription plan.'
    if (location.pathname === ADMIN_PATH) return 'Your admin dashboard.'
  }

  if (!allowedLocations.includes(location.pathname as (typeof allowedLocations)[number]))
    return null

  return (
    <header className="z-10 flex w-full flex-col border-b border-border bg-card px-6">
      <div className="mx-auto flex w-full max-w-screen-xl items-center justify-between py-8 md:py-12"> {/* Adjusted padding for responsiveness */}
        <div className="flex flex-col items-start gap-2">
          <h1 className="text-2xl md:text-3xl font-medium text-primary/80">{headerTitle()}</h1> {/* Responsive text size */}
          <p className="text-sm md:text-base font-normal text-primary/60">{headerDescription()}</p> {/* Responsive text size */}
        </div>
        <div className="flex items-center gap-4">
          {isSignedIn ? (
            <>
              {/* Optional: Display user's name or a welcome message */}
              {/* <span className="text-sm text-primary/80 hidden md:block">
                Welcome, {user?.firstName || user?.username}
              </span> */}
              <UserButton afterSignOutUrl="/auth/sign-in" />
            </>
          ) : (
            <>
              <Link to="/auth/sign-in" className="text-sm font-medium text-primary/80 hover:text-primary transition-colors">
                Sign In
              </Link>
              <Link 
                to="/auth/sign-up" 
                className="text-sm font-medium bg-blue-500 text-white px-3 py-2 rounded-md hover:bg-blue-600 transition-colors" // Example button style
              >
                Sign Up
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
