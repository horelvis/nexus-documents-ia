"use client"

import { NavLink } from "@/components/ui/nav-link"
import {
  type Icon,
} from "@tabler/icons-react"
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { useUpload } from "@/contexts/upload-context"

export function NavDocuments({
  items,
}: {
  items: {
    name: string
    url: string
    icon: Icon
  }[]
}) {
  const { openUploadDialog } = useUpload()

  const handleUploadClick = () => {
    openUploadDialog()
  }

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden">
      <SidebarGroupLabel>Quick Actions</SidebarGroupLabel>
      <SidebarMenu>
        {items.map((item) => (
          <SidebarMenuItem key={item.name}>
            {item.name === "Upload Document" ? (
              <SidebarMenuButton onClick={handleUploadClick}>
                <item.icon />
                <span>{item.name}</span>
              </SidebarMenuButton>
            ) : (
              <SidebarMenuButton asChild>
                <NavLink href={item.url}>
                  <item.icon />
                  <span>{item.name}</span>
                </NavLink>
              </SidebarMenuButton>
            )}
          </SidebarMenuItem>
        ))}
      </SidebarMenu>
    </SidebarGroup>
  )
}
