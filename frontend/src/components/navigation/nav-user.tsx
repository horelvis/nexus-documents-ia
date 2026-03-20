"use client"

/**
 * NavUser Component (SaaS Version)
 *
 * Wraps the shared UserMenu component with SaaS-specific features:
 * - Clerk authentication integration
 * - Stripe billing portal
 * - Subscription plan badges
 * - Language selector
 * - Sidebar integration
 */

import {
  IconCrown,
  IconReceipt,
  IconLanguage,
  IconNotification,
  IconUserCircle,
  IconDotsVertical,
} from "@tabler/icons-react"
import { useUser, useClerk } from "@clerk/nextjs"
import { useApiClient } from "@/lib/api-client"
import { useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { useUserContext } from "@/contexts/user-context"
import { useLanguage } from "@/contexts/language-context"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  DropdownMenuGroup,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { UserMenu as SharedUserMenu, type UserMenuUser, type UserMenuNavItem } from "@/components/ui/user-menu"
import { User, Crown, Receipt, Bell } from "lucide-react"

export function NavUser({
  user: fallbackUser,
}: {
  user?: {
    name: string
    email: string
    avatar: string
  }
}) {
  const { isMobile } = useSidebar()
  const { user: clerkUser } = useUser()
  const { signOut, openUserProfile } = useClerk()
  const { backendUser } = useUserContext()
  const { t, language, setLanguage, availableLanguages } = useLanguage()
  const apiClient = useApiClient()
  const router = useRouter()
  const params = useParams()
  const [isLoadingBilling, setIsLoadingBilling] = useState(false)

  const tenantId = params.tenantId as string

  // Use Clerk user data as primary source
  const clerkEmail = clerkUser?.primaryEmailAddress?.emailAddress || ''
  const isPlaceholderEmail = clerkEmail.includes('@clerk.local') || clerkEmail.startsWith('user_')
  const clerkName = clerkUser?.fullName || clerkUser?.firstName || ''
  const displayName = clerkName || backendUser?.full_name || 'User'
  const displayEmail = isPlaceholderEmail ? displayName : clerkEmail

  const user = clerkUser ? {
    name: displayName,
    email: displayEmail,
    avatar: clerkUser.imageUrl || ''
  } : fallbackUser || { name: 'User', email: '', avatar: '' }

  // Map to SharedUserMenu format
  const userMenuUser: UserMenuUser = {
    id: clerkUser?.id || 'user',
    email: user.email,
    fullName: user.name,
    avatarUrl: user.avatar,
    tenantId: tenantId,
    planName: getPlanBadge().name,
  }

  const handleSignOut = () => {
    signOut()
  }

  const handleAccountSettings = () => {
    try {
      if (openUserProfile) {
        openUserProfile()
      } else {
        window.location.href = '/user-profile'
      }
    } catch (error) {
      console.error('Error opening user profile:', error)
      window.location.href = '/user-profile'
    }
  }

  const handleBillingPortal = async () => {
    if (isLoadingBilling) return

    const userPlan = backendUser?.subscription_plan || 'free'

    if (userPlan === 'free') {
      if (tenantId) {
        router.push(`/${tenantId}/billing`)
      }
      return
    }

    setIsLoadingBilling(true)
    try {
      const response = await apiClient.post<{ portal_url: string }>('/stripe/create-customer-portal')

      if (response.data?.portal_url) {
        window.open(response.data.portal_url, '_blank')
      } else {
        console.error('No portal URL received')
        if (tenantId) {
          router.push(`/${tenantId}/billing`)
        }
      }
    } catch (error) {
      console.error('Error opening billing portal:', error)
      if (tenantId) {
        router.push(`/${tenantId}/billing`)
      }
    } finally {
      setIsLoadingBilling(false)
    }
  }

  const handleViewPlans = () => {
    if (tenantId) {
      router.push(`/${tenantId}/plans`)
    }
  }

  const handleNavigate = (href: string) => {
    if (tenantId) {
      router.push(`/${tenantId}${href}`)
    } else {
      router.push(href)
    }
  }

  // Safe translation helper for keys that might not exist
  const safeT = (key: string, fallback: string): string => {
    try {
      const result = t(key as any)
      return result === key ? fallback : result
    } catch {
      return fallback
    }
  }

  function getPlanBadge(): { name: string; variant: "default" | "secondary" | "destructive" | "outline" } {
    const planType = backendUser?.subscription_plan || 'free'
    const planConfigs: Record<string, { nameKey: string; fallback: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
      'free': { nameKey: 'plans.free', fallback: 'Free', variant: 'secondary' },
      'trial': { nameKey: 'plans.trial', fallback: 'Trial', variant: 'outline' },
      'pro': { nameKey: 'plans.professional', fallback: 'Professional', variant: 'default' },
      'professional': { nameKey: 'plans.professional', fallback: 'Professional', variant: 'default' },
      'enterprise': { nameKey: 'plans.enterprise', fallback: 'Enterprise', variant: 'destructive' }
    }

    const config = planConfigs[planType] || { nameKey: planType, fallback: planType, variant: 'secondary' as const }
    return { name: safeT(config.nameKey, config.fallback), variant: config.variant }
  }

  // Navigation items for SharedUserMenu
  const navItems: UserMenuNavItem[] = [
    {
      label: safeT('account.myAccount', 'My Account'),
      href: '/account',
      icon: <User className="mr-3 h-4 w-4 text-muted-foreground" />,
    },
    {
      label: safeT('account.notifications', 'Notifications'),
      href: '/notifications',
      icon: <Bell className="mr-3 h-4 w-4 text-muted-foreground" />,
    },
  ]

  // Extra navigation section for SaaS (plans & billing)
  const extraNavSection = (
    <DropdownMenuGroup>
      <DropdownMenuItem onClick={handleViewPlans} className="cursor-pointer">
        <Crown className="mr-3 h-4 w-4 text-muted-foreground" />
        {safeT('plans.viewPlans', 'View Plans')}
      </DropdownMenuItem>
      {backendUser?.is_superuser && (
        <DropdownMenuItem onClick={handleBillingPortal} disabled={isLoadingBilling} className="cursor-pointer">
          <Receipt className="mr-3 h-4 w-4 text-muted-foreground" />
          {isLoadingBilling ? safeT('account.opening', 'Opening...') :
           (backendUser?.subscription_plan && backendUser.subscription_plan !== 'free'
             ? safeT('plans.billingPortal', 'Billing Portal')
             : safeT('plans.invoicesAndPayments', 'Invoices & Payments'))}
        </DropdownMenuItem>
      )}
    </DropdownMenuGroup>
  )

  // Extra preferences section for language selector
  const extraPreferencesSection = (
    <div className="px-2 py-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm flex items-center gap-2">
          <IconLanguage className="h-4 w-4" />
          {safeT('common.language', 'Language')}
        </span>
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value as any)}
          className="text-xs border rounded px-2 py-1 bg-background"
        >
          {availableLanguages.map(lang => (
            <option key={lang.code} value={lang.code}>
              {lang.name}
            </option>
          ))}
        </select>
      </div>
    </div>
  )

  // i18n labels
  const labels = {
    account: safeT('account.account', 'Account'),
    preferences: safeT('account.preferences', 'Preferences'),
    theme: safeT('common.theme', 'Theme'),
    themeLight: safeT('common.themeLight', 'Light'),
    themeDark: safeT('common.themeDark', 'Dark'),
    themeSystem: safeT('common.themeSystem', 'System'),
    keyboardShortcuts: safeT('common.keyboardShortcuts', 'Keyboard Shortcuts'),
    help: safeT('account.helpAndSupport', 'Help & Support'),
    logout: safeT('account.signOut', 'Sign Out'),
    user: safeT('common.user', 'User'),
  }

  // Custom keyboard shortcuts for SaaS
  const keyboardShortcuts = [
    { label: safeT('shortcuts.newDocument', 'New Document'), shortcut: '⌘ N' },
    { label: safeT('shortcuts.search', 'Search'), shortcut: '⌘ K' },
    { label: safeT('shortcuts.settings', 'Settings'), shortcut: '⇧ S' },
  ]

  // Get user initials
  const userInitials = user.name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2) || 'CN'

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SharedUserMenu
          user={userMenuUser}
          navItems={navItems}
          onLogout={handleSignOut}
          onNavigate={handleNavigate}
          showThemeToggle={true}
          showKeyboardShortcuts={true}
          keyboardShortcuts={keyboardShortcuts}
          showHelp={true}
          extraNavSection={extraNavSection}
          extraPreferencesSection={extraPreferencesSection}
          planBadgeVariant={getPlanBadge().variant}
          labels={labels}
        >
          {/* Custom trigger for sidebar context */}
          <SidebarMenuButton
            size="lg"
            className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground user-nav-trigger"
          >
            <Avatar className="h-8 w-8 rounded-lg grayscale">
              <AvatarImage src={user.avatar} alt={user.name} />
              <AvatarFallback className="rounded-lg">{userInitials}</AvatarFallback>
            </Avatar>
            <div className="grid flex-1 text-left text-sm leading-tight">
              <span className="truncate font-medium">{user.name}</span>
              <span className="text-muted-foreground truncate text-xs">
                {user.email}
              </span>
            </div>
            <IconDotsVertical className="ml-auto size-4" />
          </SidebarMenuButton>
        </SharedUserMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
