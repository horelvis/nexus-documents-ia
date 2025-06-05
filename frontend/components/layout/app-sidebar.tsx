"use client"

import * as React from "react"
import { useUser } from "@clerk/nextjs"
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
    },
    {
      title: "Documents",
      url: "/dashboard/documents",
      icon: IconFiles,
      items: [
        {
          title: "Document Library",
          url: "/dashboard/documents",
        },
        {
          title: "Recent Documents",
          url: "/dashboard/documents/recent",
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
          url: "/dashboard/search",
        },
        {
          title: "AI Chat",
          url: "/dashboard/chat",
        },
        {
          title: "Document Insights",
          url: "/dashboard/insights",
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
          url: "/dashboard/agents",
        },
        {
          title: "Conversations",
          url: "/dashboard/agents/conversations",
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
          url: "/dashboard/signatures/requests",
        },
        {
          title: "Signature History",
          url: "/dashboard/signatures/history",
        },
      ],
    },
    {
      title: "Analytics",
      url: "/dashboard/analytics",
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
      url: "/dashboard/search",
      icon: IconSearch,
    },
    {
      name: "Start AI Chat",
      url: "/dashboard/chat",
      icon: IconMessages,
    },
  ],
  navSecondary: [
    {
      title: "Tenant Settings",
      url: "/dashboard/settings/tenant",
      icon: IconSettings,
    },
    {
      title: "User Management",
      url: "/dashboard/admin/users",
      icon: IconUsers,
    },
    {
      title: "Billing",
      url: "/dashboard/billing",
      icon: IconCreditCard,
    },
    {
      title: "Storage",
      url: "/dashboard/storage",
      icon: IconDatabase,
    },
    {
      title: "Help",
      url: "/dashboard/help",
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

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
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
        <NavMain items={data.navMain} />
        <NavDocuments items={data.quickActions} />
        <NavSecondary items={data.navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={data.user} />
      </SidebarFooter>
    </Sidebar>
  )
}
