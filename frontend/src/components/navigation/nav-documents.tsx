"use client"

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
import { useUpload } from "@/contexts/upload-context"

export function NavDocuments({
  items,
}: {
  items: {
    name: string
    url: string
    icon: Icon
    color?: string
  }[]
}) {
  const { openUploadDialog } = useUpload()

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

  const handleUploadClick = () => {
    openUploadDialog()
  }

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Quick Actions</SidebarGroupLabel>
      <SidebarMenu>
        {items.map((item) => (
          <SidebarMenuItem key={item.name}>
            {item.name === "Upload Document" ? (
              <SidebarMenuButton 
                onClick={handleUploadClick}
                tooltip={item.name}
              >
                <item.icon className={cn(
                  "transition-colors",
                  item.color && iconColorClasses[item.color as keyof typeof iconColorClasses]
                )} />
                <span>{item.name}</span>
              </SidebarMenuButton>
            ) : (
              <SidebarMenuButton 
                asChild
                tooltip={item.name}
              >
                <NavLink href={item.url}>
                  <item.icon className={cn(
                    "transition-colors",
                    item.color && iconColorClasses[item.color as keyof typeof iconColorClasses]
                  )} />
                  <span>{item.name}</span>
                </NavLink>
              </SidebarMenuButton>
            )}
          </SidebarMenuItem>
        ))}
      </SidebarMenu>
    </SidebarGroup>
  )
}
