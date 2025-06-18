"use client"

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
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"

export function NavMain({
  items,
}: {
  items: {
    title: string
    url: string
    icon?: Icon
    color?: string
    items?: {
      title: string
      url: string
    }[]
  }[]
}) {
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
    <SidebarGroup>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.title}>
              {item.items ? (
                <Collapsible className="group/collapsible">
                  <CollapsibleTrigger asChild>
                    <SidebarMenuButton 
                      tooltip={item.title}
                      isActive={isActive(item.url)}
                    >
                      {item.icon && <item.icon className={cn(
                        item.color && iconColorClasses[item.color as keyof typeof iconColorClasses]
                      )} />}
                      <span>{item.title}</span>
                    </SidebarMenuButton>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <SidebarMenuSub>
                      {item.items.map((subItem) => (
                        <SidebarMenuSubItem key={subItem.title}>
                          <SidebarMenuSubButton 
                            asChild
                            isActive={isActive(subItem.url)}
                          >
                            <NavLink href={subItem.url}>
                              <span>{subItem.title}</span>
                            </NavLink>
                          </SidebarMenuSubButton>
                        </SidebarMenuSubItem>
                      ))}
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </Collapsible>
              ) : (
                <SidebarMenuButton 
                  asChild 
                  tooltip={item.title}
                  isActive={isActive(item.url)}
                >
                  <NavLink href={item.url}>
                    {item.icon && <item.icon className={cn(
                      item.color && iconColorClasses[item.color as keyof typeof iconColorClasses]
                    )} />}
                    <span>{item.title}</span>
                  </NavLink>
                </SidebarMenuButton>
              )}
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
