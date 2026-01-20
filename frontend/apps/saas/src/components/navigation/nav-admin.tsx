"use client"

import { useState } from "react"
import { NavLink } from "@/components/ui/nav-link"
import {
  type Icon,
} from "@tabler/icons-react"
import { cn } from "@/lib/utils"
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { useApiClient } from "@/lib/api-client"
import { toast } from "@/hooks/use-toast"
import { Loader2 } from "lucide-react"
import { useTranslation } from "@/lib/i18n/hooks"

export function NavAdmin({
  items,
}: {
  items: {
    title: string
    url: string
    icon: Icon
    color?: string
  }[]
}) {
  const { t } = useTranslation()
  const apiClient = useApiClient()
  const [loadingBilling, setLoadingBilling] = useState(false)
  
  const iconColorClasses = {
    blue: 'text-blue-600 dark:text-blue-400',
    green: 'text-green-600 dark:text-green-400',
    purple: 'text-purple-600 dark:text-purple-400',
    orange: 'text-orange-600 dark:text-orange-400',
    pink: 'text-pink-600 dark:text-pink-400',
    yellow: 'text-yellow-600 dark:text-yellow-400',
    indigo: 'text-indigo-600 dark:text-indigo-400',
    gray: 'text-gray-600 dark:text-gray-400'
  }

  const handleBillingClick = async (e: React.MouseEvent) => {
    e.preventDefault()
    setLoadingBilling(true)
    
    try {
      // Use current URL as return URL
      const returnUrl = window.location.href
      const response = await apiClient.post<{ portal_url: string }>('/stripe/create-customer-portal', {
        return_url: returnUrl
      })
      if (!response.error && response.data?.portal_url) {
        // Small delay to show loading state
        setTimeout(() => {
          window.location.href = response.data.portal_url
        }, 300)
      } else {
        // Check if it's a configuration error
        if (response.error?.includes('No configuration provided')) {
          toast({
            title: 'Billing Portal Not Configured',
            description: 'The billing portal needs to be configured in Stripe. Please contact support.',
            variant: 'destructive'
          })
        } else {
          throw new Error(response.error || 'Failed to open billing portal')
        }
        setLoadingBilling(false)
      }
    } catch (error) {
      setLoadingBilling(false)
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to open billing portal',
        variant: 'destructive'
      })
    }
  }

  // Don't render anything if no items
  if (!items || items.length === 0) {
    return null
  }

  return (
    <SidebarGroup>
      <SidebarGroupLabel>{t('sidebar.adminActions')}</SidebarGroupLabel>
      <SidebarMenu>
        {items.map((item) => (
          <SidebarMenuItem key={item.title}>
            {item.title === "Billing" ? (
              <SidebarMenuButton 
                onClick={handleBillingClick} 
                disabled={loadingBilling}
                tooltip={item.title}
              >
                {loadingBilling ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <item.icon className={cn(
                    "transition-colors",
                    item.color && iconColorClasses[item.color as keyof typeof iconColorClasses]
                  )} />
                )}
                <span>{loadingBilling ? "Loading..." : item.title}</span>
              </SidebarMenuButton>
            ) : (
              <SidebarMenuButton 
                asChild
                tooltip={item.title}
              >
                <NavLink href={item.url}>
                  <item.icon className={cn(
                    "transition-colors",
                    item.color && iconColorClasses[item.color as keyof typeof iconColorClasses]
                  )} />
                  <span>{item.title}</span>
                </NavLink>
              </SidebarMenuButton>
            )}
          </SidebarMenuItem>
        ))}
      </SidebarMenu>
    </SidebarGroup>
  )
}