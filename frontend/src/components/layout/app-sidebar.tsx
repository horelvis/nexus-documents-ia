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
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/auth-context'
import {
  IconPlug,
  IconSettings,
  IconHelp,
  IconHistory,
  IconPlus,
  IconSchool,
  IconDashboard,
  IconMessageCircle,
  IconFileText,
  IconBell,
  IconNetwork,
  IconRobot,
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
} from '@/components/ui'
import { UserMenu } from '@/components/user-menu'

interface AppSidebarProps extends React.ComponentProps<typeof Sidebar> {
  onNewConversation?: () => void
  onOpenHistory?: () => void
}

export function AppSidebar({ onNewConversation, onOpenHistory, ...props }: AppSidebarProps) {
  const { isAdmin } = useAuth()
  const pathname = usePathname()
  const router = useRouter()

  // Handle new conversation - use provided handler or navigate to home
  const handleNewConversation = () => {
    if (onNewConversation) {
      onNewConversation()
    } else {
      router.push('/')
    }
  }

  // Handle history - use provided handler or navigate to home with query param
  const handleOpenHistory = () => {
    if (onOpenHistory) {
      onOpenHistory()
    } else {
      router.push('/?history=open')
    }
  }

  const mainNavItems = [
    {
      title: 'Nueva consulta',
      icon: IconPlus,
      onClick: handleNewConversation,
      isActive: false,
    },
    {
      title: 'Historial',
      icon: IconHistory,
      onClick: handleOpenHistory,
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
      title: 'Documentos',
      href: '/documents',
      icon: IconFileText,
    },
    {
      title: 'Agentes',
      href: '/agents',
      icon: IconRobot,
    },
    {
      title: 'Data Learning',
      href: '/data-learning',
      icon: IconSchool,
    },
    {
      title: 'Inteligencia Proactiva',
      href: '/insights',
      icon: IconBell,
    },
    {
      title: 'Configuración',
      href: '/settings',
      icon: IconSettings,
    },
  ]

  const adminNavItems = [
    {
      title: 'Administración',
      href: '/admin/dashboard',
      icon: IconDashboard,
    },
    {
      title: 'Agentes',
      href: '/admin/agents',
      icon: IconRobot,
    },
    {
      title: 'Knowledge Graph',
      href: '/knowledge-graph',
      icon: IconNetwork,
    },
    {
      title: 'Canales',
      href: '/emma/channels',
      icon: IconMessageCircle,
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
                <img
                  src="/logo-single.png"
                  alt="NouxCube AI"
                  className="h-8 w-8 object-contain"
                />
                <span className="font-semibold">NouxCube <span className="text-muted-foreground">AI</span></span>
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

        {/* Admin — only visible to admin users */}
        {isAdmin && (
        <SidebarGroup>
          <SidebarGroupLabel>Admin</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {adminNavItems.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    tooltip={item.title}
                    isActive={pathname === item.href || pathname.startsWith(item.href)}
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
        )}

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
