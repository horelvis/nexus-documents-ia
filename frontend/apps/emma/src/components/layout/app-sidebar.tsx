'use client'

/**
 * Emma App Sidebar
 *
 * Sidebar navigation component for Emma on-premise deployment.
 * Uses shadcn sidebar components from the shared package.
 * Follows shadcn sidebar pattern with offcanvas collapsible and inset variant.
 */

import * as React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  IconBrain,
  IconPlug,
  IconSettings,
  IconHelp,
  IconHistory,
  IconPlus,
  IconSchool,
} from '@tabler/icons-react'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@nexus/shared/ui'
import { UserMenu } from '@/components/user-menu'

interface AppSidebarProps extends React.ComponentProps<typeof Sidebar> {
  onNewConversation?: () => void
  onOpenHistory?: () => void
}

export function AppSidebar({ onNewConversation, onOpenHistory, ...props }: AppSidebarProps) {
  const pathname = usePathname()

  const mainNavItems = [
    {
      title: 'Nueva consulta',
      icon: IconPlus,
      onClick: onNewConversation,
      isActive: false,
    },
    {
      title: 'Historial',
      icon: IconHistory,
      onClick: onOpenHistory,
      isActive: false,
    },
  ]

  const configNavItems = [
    {
      title: 'Conectores',
      href: '/connectors',
      icon: IconPlug,
    },
    {
      title: 'Data Learning',
      href: '/data-learning',
      icon: IconSchool,
    },
    {
      title: 'Configuración',
      href: '/settings',
      icon: IconSettings,
    },
  ]

  const secondaryNavItems = [
    {
      title: 'Ayuda',
      href: '/help',
      icon: IconHelp,
    },
  ]

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              size="lg"
              className="data-[slot=sidebar-menu-button]:!p-1.5"
            >
              <Link href="/">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10">
                  <IconBrain className="h-5 w-5 text-primary" />
                </div>
                <div className="flex flex-col gap-0.5 leading-none">
                  <span className="font-semibold">Emma</span>
                  <span className="text-xs text-muted-foreground">Intelligence</span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {/* Main Navigation */}
        <SidebarGroup>
          <SidebarGroupLabel>Chat</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {mainNavItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton
                    tooltip={item.title}
                    isActive={item.isActive}
                    onClick={item.onClick}
                  >
                    <item.icon className="h-4 w-4" />
                    <span>{item.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Configuration */}
        <SidebarGroup>
          <SidebarGroupLabel>Configuración</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {configNavItems.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    tooltip={item.title}
                    isActive={pathname === item.href}
                  >
                    <Link href={item.href}>
                      <item.icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Secondary Navigation */}
        <SidebarGroup className="mt-auto">
          <SidebarGroupContent>
            <SidebarMenu>
              {secondaryNavItems.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    tooltip={item.title}
                    isActive={pathname === item.href}
                  >
                    <Link href={item.href}>
                      <item.icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <UserMenu />
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
