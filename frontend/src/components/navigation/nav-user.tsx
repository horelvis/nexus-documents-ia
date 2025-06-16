"use client"

import {
  IconCreditCard,
  IconDotsVertical,
  IconLogout,
  IconNotification,
  IconUserCircle,
  IconCrown,
  IconReceipt,
} from "@tabler/icons-react"
import { useUser, useClerk } from "@clerk/nextjs"
import { useApiClient } from "@/lib/api-client"
import { useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { useUserContext } from "@/contexts/user-context"
import { Badge } from "@/components/ui/badge"

import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"

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
  const apiClient = useApiClient()
  const router = useRouter()
  const params = useParams()
  const [isLoadingBilling, setIsLoadingBilling] = useState(false)
  
  const tenantId = params.tenantId as string

  // Use Clerk user data if available, fallback to prop
  const user = clerkUser ? {
    name: clerkUser.fullName || clerkUser.firstName || 'User',
    email: clerkUser.primaryEmailAddress?.emailAddress || '',
    avatar: clerkUser.imageUrl || ''
  } : fallbackUser || { name: 'User', email: '', avatar: '' }

  const handleSignOut = () => {
    signOut()
  }

  const handleAccountSettings = () => {
    // Use Clerk's hook to open user profile
    // This will open Clerk's UserProfile modal/component
    try {
      if (openUserProfile) {
        openUserProfile()
      } else {
        // Fallback: redirect to user profile page in your app
        window.location.href = '/user-profile'
      }
    } catch (error) {
      console.error('Error opening user profile:', error)
      // Fallback: redirect to user profile page in your app
      window.location.href = '/user-profile'
    }
  }

  const handleBillingPortal = async () => {
    if (isLoadingBilling) return
    
    // Check if user has a paid plan
    const userPlan = backendUser?.subscription_plan || 'free'
    
    // If free plan, redirect to billing page with tenantId
    if (userPlan === 'free') {
      if (tenantId) {
        router.push(`/${tenantId}/billing`)
      }
      return
    }
    
    // For paid plans, open Stripe customer portal
    setIsLoadingBilling(true)
    try {
      const response = await apiClient.post<{ portal_url: string }>('/stripe/create-customer-portal')
      
      if (response.data?.portal_url) {
        window.open(response.data.portal_url, '_blank')
      } else {
        console.error('No portal URL received')
        // Fallback to billing page with tenantId
        if (tenantId) {
          router.push(`/${tenantId}/billing`)
        }
      }
    } catch (error) {
      console.error('Error opening billing portal:', error)
      // Fallback to billing page with tenantId
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

  const getPlanBadge = () => {
    // Use subscription_plan from backend user (populated from Stripe)
    const planType = backendUser?.subscription_plan || 'free'
    const planConfigs: Record<string, { name: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
      'free': { name: 'Gratuito', variant: 'secondary' },
      'pro': { name: 'Profesional', variant: 'default' },
      'professional': { name: 'Profesional', variant: 'default' },
      'enterprise': { name: 'Empresarial', variant: 'destructive' }
    }
    
    return planConfigs[planType] || { name: planType, variant: 'secondary' }
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            >
              <Avatar className="h-8 w-8 rounded-lg grayscale">
                <AvatarImage src={user.avatar} alt={user.name} />
                <AvatarFallback className="rounded-lg">CN</AvatarFallback>
              </Avatar>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-medium">{user.name}</span>
                <span className="text-muted-foreground truncate text-xs">
                  {user.email}
                </span>
              </div>
              <IconDotsVertical className="ml-auto size-4" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
            side={isMobile ? "bottom" : "right"}
            align="end"
            sideOffset={4}
          >
            <DropdownMenuLabel className="p-0 font-normal">
              <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                <Avatar className="h-8 w-8 rounded-lg">
                  <AvatarImage src={user.avatar} alt={user.name} />
                  <AvatarFallback className="rounded-lg">CN</AvatarFallback>
                </Avatar>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium">{user.name}</span>
                  <span className="text-muted-foreground truncate text-xs">
                    {user.email}
                  </span>
                </div>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            
            {/* Plan actual */}
            <div className="px-2 py-1.5">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Plan actual</span>
                <Badge variant={getPlanBadge().variant} className="text-xs">
                  {getPlanBadge().name}
                </Badge>
              </div>
            </div>
            
            <DropdownMenuSeparator />
            
            <DropdownMenuGroup>
              <DropdownMenuItem onClick={handleAccountSettings}>
                <IconUserCircle />
                Mi cuenta
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleViewPlans}>
                <IconCrown />
                Ver planes
              </DropdownMenuItem>
              {backendUser?.is_superuser && (
                <DropdownMenuItem onClick={handleBillingPortal} disabled={isLoadingBilling}>
                  <IconReceipt />
                  {isLoadingBilling ? 'Abriendo...' : 
                   (backendUser?.subscription_plan && backendUser.subscription_plan !== 'free' 
                     ? 'Portal de facturación' 
                     : 'Facturas y pagos')}
                </DropdownMenuItem>
              )}
              <DropdownMenuItem>
                <IconNotification />
                Notificaciones
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleSignOut}>
              <IconLogout />
              Cerrar sesión
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
