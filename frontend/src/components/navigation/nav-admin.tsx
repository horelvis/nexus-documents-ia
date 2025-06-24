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
    try {
      // Use current URL as return URL
      const returnUrl = window.location.href
      const response = await apiClient.post<{ portal_url: string }>('/stripe/create-customer-portal', {
        return_url: returnUrl
      })
      if (!response.error && response.data?.portal_url) {
        window.location.href = response.data.portal_url
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
      }
    } catch (error) {
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
    <SidebarGroup className="group-data-[collapsible=icon]:hidden">
      <SidebarGroupLabel>Admin Actions</SidebarGroupLabel>
      <SidebarMenu>
        {items.map((item) => (
          <SidebarMenuItem key={item.title}>
            {item.title === "Billing" ? (
              <SidebarMenuButton onClick={handleBillingClick}>
                <item.icon className={cn(
                  item.color && iconColorClasses[item.color as keyof typeof iconColorClasses]
                )} />
                <span>{item.title}</span>
              </SidebarMenuButton>
            ) : (
              <SidebarMenuButton asChild>
                <NavLink href={item.url}>
                  <item.icon className={cn(
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