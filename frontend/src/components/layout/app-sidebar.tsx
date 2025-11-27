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

import { useTranslation } from "@/lib/i18n/hooks"

export function AppSidebar({ tenantId, ...props }: AppSidebarProps) {
  const { backendUser } = useBackendUser()
  const { t } = useTranslation()

  // Check if user is admin (superuser, has admin role, or is not a team member)
  const isTenantAdmin = backendUser && (
    backendUser.is_superuser ||
    backendUser.roles?.some((role: any) => role.name === 'admin') ||
    !backendUser.is_team_member
  )

  const data = {
    user: {
      name: "shadcn",
      email: "m@example.com",
      avatar: "/avatars/shadcn.jpg",
    },
    navMain: [
      {
        title: t('sidebar.dashboard'),
        url: "/dashboard",
        icon: IconDashboard,
        color: "blue",
      },
      {
        title: t('sidebar.documents.title'),
        url: "/documents",
        icon: IconFiles,
        color: "green",
        items: [
          {
            title: t('sidebar.documents.library'),
            url: "/documents",
          },
          {
            title: t('sidebar.documents.shared'),
            url: "/shared",
          },
        ],
      },
      {
        title: t('sidebar.search'),
        url: "/search",
        icon: IconBrain,
        color: "purple",
      },
      {
        title: t('sidebar.workflows.title'),
        url: "/workflows",
        icon: IconGitBranch,
        color: "cyan",
        items: [
          {
            title: t('sidebar.workflows.agents'),
            url: "/workflows/ai-agents",
          },
          {
            title: t('sidebar.workflows.builder'),
            url: "/workflows/builder",
          },
          {
            title: t('sidebar.workflows.renewals'),
            url: "/workflows/contract-renewal",
          },
          {
            title: t('sidebar.workflows.library'),
            url: "/workflows/library",
          },
          {
            title: t('sidebar.workflows.analytics'),
            url: "/workflows/analytics",
          },
        ],
      },
      {
        title: t('sidebar.signatures.title'),
        url: "/signatures/requests",
        icon: IconSignature,
        color: "pink",
        items: [
          {
            title: t('sidebar.signatures.requests'),
            url: "/signatures/requests",
          },
          {
            title: t('sidebar.signatures.history'),
            url: "/signatures/history",
          },
        ],
      },
      {
        title: t('sidebar.analytics'),
        url: "/analytics",
        icon: IconChartBar,
        color: "orange",
      },
    ],
    quickActions: [
      {
        name: t('sidebar.quickActions.upload'),
        url: "#", // Will be handled by context
        icon: IconCloudUpload,
        color: "blue",
      },
      {
        name: t('sidebar.quickActions.askEmma'),
        url: "/chat",
        icon: IconBrain,
        color: "purple",
      },
      {
        name: t('sidebar.quickActions.createWorkflow'),
        url: "/workflows/builder",
        icon: IconRobot,
        color: "cyan",
      },
      {
        name: t('sidebar.quickActions.sign'),
        url: "/signatures/requests",
        icon: IconSignature,
        color: "pink",
      },
    ],
    adminActions: [
      {
        title: t('sidebar.admin.teams'),
        url: "/admin/teams",
        icon: IconUsers,
        color: "indigo",
      },
      {
        title: t('sidebar.admin.settings'),
        url: "/settings/tenant",
        icon: IconSettings,
        color: "gray",
      },
      {
        title: t('sidebar.admin.providers'),
        url: "/admin/signature-providers",
        icon: IconSignature,
        color: "pink",
      },
      {
        title: t('sidebar.admin.billing'),
        url: "/billing",
        icon: IconCreditCard,
        color: "green",
      },
    ],
    navSecondary: [
      {
        title: t('sidebar.storage'),
        url: "/storage",
        icon: IconDatabase,
        color: "purple",
      },
      {
        title: t('sidebar.help'),
        url: "/help",
        icon: IconHelp,
        color: "orange",
      },
    ],
    recentDocuments: [
      {
        name: t('sidebar.documents.recent'),
        url: "/documents/recent",
        icon: IconClock,
      },
      {
        name: t('sidebar.documents.popular'),
        url: "/documents/popular",
        icon: IconTrendingUp,
      },
      {
        name: t('sidebar.documents.sharedWithMe'),
        url: "/documents/shared",
        icon: IconUserCheck,
      },
    ],
  }

  const buildNavMain = React.useCallback(() => {
    const baseNav = [...data.navMain]
    if (isTenantAdmin) {
      const templateItem = {
        title: t('sidebar.admin.templates'),
        url: "/templates",
        icon: IconFileText,
        color: "orange",
      }
      const insertIndex = baseNav.findIndex(item => item.title === t('sidebar.signatures.title'))
      if (insertIndex >= 0) {
        baseNav.splice(insertIndex, 0, templateItem)
      } else {
        baseNav.push(templateItem)
      }
    }
    return baseNav
  }, [isTenantAdmin, t, data.navMain])

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
    <Sidebar collapsible="icon" id="main-sidebar" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              className="data-[slot=sidebar-menu-button]:!p-1.5"
              tooltip={t('sidebar.nexusDocument')}
            >
              <NavLink href={`/${tenantId}/dashboard`}>
                <IconInnerShadowTop className="!size-5" />
                <span className="text-base font-semibold">{t('sidebar.nexusDocument')}</span>
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
