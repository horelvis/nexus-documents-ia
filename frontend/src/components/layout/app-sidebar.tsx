"use client"

import * as React from "react"
import type { AppSidebarProps } from '@/lib/types'
import {
  IconCloudUpload,
  IconSearch,
  IconBrain,
  IconRobot,
  IconMessages,
  IconSignature,
  IconChartBar,
  IconDashboard,
  IconFiles,
  IconClock,
  IconTrendingUp,
  IconUsers,
  IconSettings,
  IconCreditCard,
  IconDatabase,
  IconHelp,
  IconInnerShadowTop,
  IconUserCheck,
} from "@tabler/icons-react"

import { NavDocuments } from "@/components/navigation/nav-documents"
import { NavMain } from "@/components/navigation/nav-main"
import { NavSecondary } from "@/components/navigation/nav-secondary"
import { NavUser } from "@/components/navigation/nav-user"
import { NavAgents } from "@/components/navigation/nav-agents"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

const data = {
  user: {
    name: "shadcn",
    email: "m@example.com",
    avatar: "/avatars/shadcn.jpg",
  },
  navMain: [
    {
      title: "Dashboard",
      url: "/dashboard",
      icon: IconDashboard,
    },
    {
      title: "Documents",
      url: "/documents",
      icon: IconFiles,
      items: [
        {
          title: "Document Library",
          url: "/documents",
        },
        {
          title: "Recent Documents",
          url: "/documents/recent",
        },
      ],
    },
    {
      title: "Search & AI",
      url: "#",
      icon: IconBrain,
      items: [
        {
          title: "Semantic Search",
          url: "/search",
        },
        {
          title: "AI Chat",
          url: "/chat",
        },
        {
          title: "Document Insights",
          url: "/insights",
        },
      ],
    },
    {
      title: "AI Agents",
      url: "#",
      icon: IconRobot,
      items: [
        {
          title: "Agent Library",
          url: "/agents",
        },
        {
          title: "Conversations",
          url: "/agents/conversations",
        },
      ],
    },
    {
      title: "Digital Signatures",
      url: "#",
      icon: IconSignature,
      items: [
        {
          title: "Signature Requests",
          url: "/signatures/requests",
        },
        {
          title: "Signature History",
          url: "/signatures/history",
        },
      ],
    },
    {
      title: "Analytics",
      url: "/analytics",
      icon: IconChartBar,
    },
  ],
  quickActions: [
    {
      name: "Upload Document", 
      url: "#", // Will be handled by context
      icon: IconCloudUpload,
    },
    {
      name: "Search",
      url: "/search",
      icon: IconSearch,
    },
    {
      name: "Start AI Chat",
      url: "/chat",
      icon: IconMessages,
    },
  ],
  navSecondary: [
    {
      title: "Tenant Settings",
      url: "/settings/tenant",
      icon: IconSettings,
    },
    {
      title: "User Management",
      url: "/admin/users",
      icon: IconUsers,
    },
    {
      title: "Billing",
      url: "/billing",
      icon: IconCreditCard,
    },
    {
      title: "Storage",
      url: "/storage",
      icon: IconDatabase,
    },
    {
      title: "Help",
      url: "/help",
      icon: IconHelp,
    },
  ],
  recentDocuments: [
    {
      name: "Recent uploads",
      url: "/documents/recent",
      icon: IconClock,
    },
    {
      name: "Most viewed",
      url: "/documents/popular",
      icon: IconTrendingUp,
    },
    {
      name: "Shared with me",
      url: "/documents/shared",
      icon: IconUserCheck,
    },
  ],
}

export function AppSidebar({ tenantId, ...props }: AppSidebarProps) {
  // Generate tenant-aware navigation data
  const getNavData = () => {
    const basePath = tenantId ? `/${tenantId}` : '';
    
    return {
      ...data,
      navMain: data.navMain.map(item => ({
        ...item,
        url: item.url.startsWith('#') ? item.url : `${basePath}${item.url}`,
        items: item.items?.map(subItem => ({
          ...subItem,
          url: `${basePath}${subItem.url}`
        }))
      })),
      navSecondary: data.navSecondary.map(item => ({
        ...item,
        url: `${basePath}${item.url}`
      }))
    };
  };

  const navData = getNavData();

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              className="data-[slot=sidebar-menu-button]:!p-1.5"
            >
              <a href="#">
                <IconInnerShadowTop className="!size-5" />
                <span className="text-base font-semibold">Nexus Document</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navData.navMain} />
        <NavDocuments items={navData.quickActions} />
        <NavAgents />
        <NavSecondary items={navData.navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={navData.user} />
      </SidebarFooter>
    </Sidebar>
  )
}
