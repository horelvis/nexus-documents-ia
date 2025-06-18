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
      color: "blue",
    },
    {
      title: "Documents",
      url: "/documents",
      icon: IconFiles,
      color: "green",
      items: [
        {
          title: "Document Library",
          url: "/documents",
        },
        {
          title: "Recent Documents",
          url: "/documents/recent",
        },
        {
          title: "Shared Documents",
          url: "/shared",
        },
      ],
    },
    {
      title: "Search & AI",
      url: "#",
      icon: IconBrain,
      color: "purple",
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
      color: "indigo",
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
      color: "pink",
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
      color: "orange",
    },
  ],
  quickActions: [
    {
      name: "Upload Document", 
      url: "#", // Will be handled by context
      icon: IconCloudUpload,
      color: "blue",
    },
    {
      name: "Search",
      url: "/search",
      icon: IconSearch,
      color: "green",
    },
    {
      name: "Start AI Chat",
      url: "/chat",
      icon: IconMessages,
      color: "purple",
    },
  ],
  navSecondary: [
    {
      title: "Tenant Settings",
      url: "/settings/tenant",
      icon: IconSettings,
      color: "gray",
    },
    {
      title: "User Management",
      url: "/admin/users",
      icon: IconUsers,
      color: "blue",
    },
    {
      title: "Team Management",
      url: "/admin/teams",
      icon: IconUsers,
      color: "indigo",
    },
    {
      title: "Billing",
      url: "/billing",
      icon: IconCreditCard,
      color: "green",
    },
    {
      title: "Storage",
      url: "/storage",
      icon: IconDatabase,
      color: "purple",
    },
    {
      title: "Help",
      url: "/help",
      icon: IconHelp,
      color: "orange",
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
        color: item.color,
        items: item.items?.map(subItem => ({
          ...subItem,
          url: `${basePath}${subItem.url}`
        }))
      })),
      navSecondary: data.navSecondary.map(item => ({
        ...item,
        url: `${basePath}${item.url}`,
        color: item.color
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
        <NavSecondary items={navData.navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={navData.user} />
      </SidebarFooter>
    </Sidebar>
  )
}
