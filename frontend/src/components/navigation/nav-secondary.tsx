"use client"

import * as React from "react"
import { NavLink } from "@/components/ui/nav-link"
import { type Icon } from "@tabler/icons-react"
import { useActiveRoute } from "@/hooks/use-active-route"
import { cn } from "@/lib/utils"

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

export function NavSecondary({
  items,
  ...props
}: {
  items: {
    title: string
    url: string
    icon: Icon
    color?: string
  }[]
} & React.ComponentPropsWithoutRef<typeof SidebarGroup>) {
  const { isActive } = useActiveRoute()

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

  return (
    <SidebarGroup {...props}>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton 
                asChild
                isActive={isActive(item.url)}
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
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
