"use client"

import { NavLink } from "@/components/ui/nav-link"
import { type Icon, IconChevronDown } from "@tabler/icons-react"
import { useActiveRoute } from "@/hooks/use-active-route"
import { cn } from "@/lib/utils"
import { useState, useEffect } from "react"
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
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
  const { state } = useSidebar()
  const [openItem, setOpenItem] = useState<string | null>(null)

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

  const toggleItem = (title: string) => {
    setOpenItem(prev => prev === title ? null : title)
  }

  // Close all submenus when sidebar collapses
  useEffect(() => {
    if (state === "collapsed") {
      setOpenItem(null)
    }
  }, [state])

  return (
    <SidebarGroup>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => {
            const isOpen = openItem === item.title
            const hasActiveSubItem = item.items?.some(subItem => isActive(subItem.url))
            
            return (
              <SidebarMenuItem key={item.title}>
                {item.items ? (
                  <Collapsible 
                    open={isOpen || (hasActiveSubItem && state === "expanded")} 
                    onOpenChange={() => toggleItem(item.title)}
                    className="group/collapsible"
                  >
                    <CollapsibleTrigger asChild>
                      <SidebarMenuButton 
                        tooltip={item.title}
                        isActive={hasActiveSubItem}
                        className="group cursor-pointer"
                      >
                        {item.icon && <item.icon className={cn(
                          "transition-colors",
                          item.color && iconColorClasses[item.color as keyof typeof iconColorClasses]
                        )} />}
                        <span className="flex-1">{item.title}</span>
                        {state === "expanded" && (
                          <IconChevronDown 
                            className={cn(
                              "h-4 w-4 transition-transform duration-200",
                              (isOpen || hasActiveSubItem) && "rotate-180"
                            )}
                          />
                        )}
                      </SidebarMenuButton>
                    </CollapsibleTrigger>
                    {state === "expanded" && (
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
                    )}
                  </Collapsible>
                ) : (
                  <SidebarMenuButton 
                    asChild 
                    tooltip={item.title}
                    isActive={isActive(item.url)}
                  >
                    <NavLink href={item.url}>
                      {item.icon && <item.icon className={cn(
                        "transition-colors",
                        item.color && iconColorClasses[item.color as keyof typeof iconColorClasses]
                      )} />}
                      <span>{item.title}</span>
                    </NavLink>
                  </SidebarMenuButton>
                )}
              </SidebarMenuItem>
            )
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
