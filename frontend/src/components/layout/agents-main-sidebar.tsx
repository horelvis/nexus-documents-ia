"use client"

import * as React from "react"
import { useState } from "react"
import { 
  Bot, 
  Home, 
  Settings, 
  BarChart3, 
  FileSignature,
  Command,
  Plus
} from "lucide-react"

import { NavUser } from "@/components/navigation/nav-user"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { useRouter, useParams } from "next/navigation"

const data = {
  user: {
    name: "AI Assistant",
    email: "ai@nexus.com",
    avatar: "/avatars/ai.jpg",
  },
  navMain: [
    {
      title: "Dashboard",
      url: "/dashboard",
      icon: Home,
      isActive: false,
    },
    {
      title: "AI Agents",
      url: "/agents",
      icon: Bot,
      isActive: true,
    },
    {
      title: "Signatures",
      url: "/signatures",
      icon: FileSignature,
      isActive: false,
    },
    {
      title: "Analytics",
      url: "/analytics",
      icon: BarChart3,
      isActive: false,
    },
    {
      title: "Settings",
      url: "/settings",
      icon: Settings,
      isActive: false,
    },
  ],
}

interface AgentsMainSidebarProps {
  onCreateAgent?: () => void
}

export function AgentsMainSidebar({ 
  onCreateAgent,
  ...props 
}: AgentsMainSidebarProps & React.ComponentProps<typeof Sidebar>) {
  const { setOpen } = useSidebar()
  const router = useRouter()
  const params = useParams()
  const tenantId = params.tenantId as string

  const handleNavigation = (url: string) => {
    if (tenantId) {
      router.push(`/${tenantId}${url}`)
    } else {
      router.push(url)
    }
    setOpen(true)
  }

  return (
    <Sidebar
      collapsible="none"
      className="!w-[calc(var(--sidebar-width-icon)_+_1px)] border-r"
      {...props}
    >
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild className="md:h-8 md:p-0">
              <button onClick={() => handleNavigation('/dashboard')}>
                <div className="bg-sidebar-primary text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center rounded-lg">
                  <Command className="size-4" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium">Nexus AI</span>
                  <span className="truncate text-xs">Agents Hub</span>
                </div>
              </button>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent className="px-1.5 md:px-0">
            <SidebarMenu>
              {data.navMain.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton
                    tooltip={{
                      children: item.title,
                      hidden: false,
                    }}
                    onClick={() => handleNavigation(item.url)}
                    isActive={item.isActive}
                    className="px-2.5 md:px-2"
                  >
                    <item.icon />
                    <span>{item.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
              
              {/* Divider */}
              <SidebarMenuItem>
                <div className="border-t my-2" />
              </SidebarMenuItem>
              
              {/* Quick Create Agent */}
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip={{
                    children: "Crear Nuevo Agente",
                    hidden: false,
                  }}
                  onClick={onCreateAgent}
                  className="px-2.5 md:px-2 text-green-600 hover:text-green-700 hover:bg-green-50"
                >
                  <Plus />
                  <span>Nuevo Agente</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <NavUser user={data.user} />
      </SidebarFooter>
    </Sidebar>
  )
}