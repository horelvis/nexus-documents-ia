"use client"

import * as React from "react"
import type { AppSidebarProps } from '@/lib/types'
import {
  IconCloudUpload,
  IconSearch,
  IconBrain,
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
  IconGitBranch,
  IconRobot,
  IconFileText,
} from "@tabler/icons-react"

import { NavDocuments } from "@/components/navigation/nav-documents"
import { NavMain } from "@/components/navigation/nav-main"
import { NavSecondary } from "@/components/navigation/nav-secondary"
import { NavUser } from "@/components/navigation/nav-user"
import { NavAdmin } from "@/components/navigation/nav-admin"
import { NavLink } from "@/components/ui/nav-link"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"
import { useBackendUser } from "@/contexts/user-context"

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
          title: "Shared Documents",
          url: "/shared",
        },
      ],
    },
    {
      title: "Search & AI",
      url: "/search",
      icon: IconBrain,
      color: "purple",
    },
    {
      title: "WorkFlow AI",
      url: "/workflows",
      icon: IconGitBranch,
      color: "cyan",
      items: [
        {
          title: "AI Agents Workflows",
          url: "/workflows/ai-agents",
        },
        {
          title: "Process Builder",
          url: "/workflows/builder",
        },
        {
          title: "Contract Renewals",
          url: "/workflows/contract-renewal",
        },
        {
          title: "Process Library",
          url: "/workflows/library",
        },
        {
          title: "Analytics",
          url: "/workflows/analytics",
        },
      ],
    },
    {
      title: "Digital Signatures",
      url: "/signatures/requests",
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
      name: "Ask Emma",
      url: "/chat",
      icon: IconBrain,
      color: "purple",
    },
    {
      name: "Create Workflow",
      url: "/workflows/builder",
      icon: IconRobot,
      color: "cyan",
    },
    {
      name: "Firmar Documento",
      url: "/signatures/requests",
      icon: IconSignature,
      color: "pink",
    },
  ],
  adminActions: [
    {
      title: "Team Management",
      url: "/admin/teams",
      icon: IconUsers,
      color: "indigo",
    },
    {
      title: "Tenant Settings",
      url: "/settings/tenant",
      icon: IconSettings,
      color: "gray",
    },
    {
      title: "Signature Providers",
      url: "/admin/signature-providers",
      icon: IconSignature,
      color: "pink",
    },
    {
      title: "Billing",
      url: "/billing",
      icon: IconCreditCard,
      color: "green",
    },
  ],
  navSecondary: [
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
  const { backendUser } = useBackendUser()
  
  // Check if user is admin (superuser, has admin role, or is not a team member)
  const isTenantAdmin = backendUser && (
    backendUser.is_superuser || 
    backendUser.roles?.some((role: any) => role.name === 'admin') ||
    !backendUser.is_team_member
  )
  
  // Debug log
  React.useEffect(() => {
    console.log('Sidebar - Backend user:', backendUser)
    console.log('Sidebar - Is tenant admin:', isTenantAdmin)
    console.log('Sidebar - TenantId:', tenantId)
    console.log('Sidebar - QuickActions URLs:', getNavData().quickActions.map(a => a.url))
  }, [backendUser, isTenantAdmin, tenantId])
  
  const buildNavMain = React.useCallback(() => {
    const baseNav = [...data.navMain]
    if (isTenantAdmin) {
      const templateItem = {
        title: "Document Templates",
        url: "/templates",
        icon: IconFileText,
        color: "orange",
      }
      const insertIndex = baseNav.findIndex(item => item.title === "Digital Signatures")
      if (insertIndex >= 0) {
        baseNav.splice(insertIndex, 0, templateItem)
      } else {
        baseNav.push(templateItem)
      }
    }
    return baseNav
  }, [isTenantAdmin])
  
  // Generate tenant-aware navigation data
  const getNavData = () => {
    const basePath = tenantId ? `/${tenantId}` : '';
    const navMainSource = buildNavMain()
    
    return {
      ...data,
      navMain: navMainSource.map(item => ({
        ...item,
        url: item.url.startsWith('#') ? item.url : `${basePath}${item.url}`,
        color: item.color,
        items: item.items?.map(subItem => ({
          ...subItem,
          url: `${basePath}${subItem.url}`
        }))
      })),
      quickActions: data.quickActions.map(item => ({
        ...item,
        url: item.url.startsWith('#') ? item.url : `${basePath}${item.url}`
      })),
      adminActions: isTenantAdmin ? data.adminActions.map(item => ({
        ...item,
        url: `${basePath}${item.url}`,
        color: item.color
      })) : [],
      navSecondary: data.navSecondary.map(item => ({
        ...item,
        url: `${basePath}${item.url}`,
        color: item.color
      }))
    };
  };

  const navData = getNavData();

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              className="data-[slot=sidebar-menu-button]:!p-1.5"
              tooltip="Nexus Document"
            >
              <NavLink href={`/${tenantId}/dashboard`}>
                <IconInnerShadowTop className="!size-5" />
                <span className="text-base font-semibold">Nexus Document</span>
              </NavLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navData.navMain} />
        <NavDocuments items={navData.quickActions} />
        <NavAdmin items={navData.adminActions} />
        <NavSecondary items={navData.navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={navData.user} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
