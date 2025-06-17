"use client"

import { useRouter } from "next/navigation"
import { 
  IconUpload, 
  IconSearch, 
  IconRobot,
  IconUsers,
  IconFileText,
  IconSettings,
  IconChartBar,
  IconFolderPlus
} from "@tabler/icons-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { useUpload } from "@/contexts/upload-context"

interface QuickAction {
  id: string
  title: string
  description: string
  icon: any
  action: () => void
  variant?: 'default' | 'outline' | 'secondary'
}

export function QuickActions({ tenantId }: { tenantId: string }) {
  const router = useRouter()
  const { openUploadDialog } = useUpload()

  const actions: QuickAction[] = [
    {
      id: 'upload',
      title: 'Upload Documents',
      description: 'Add new files to your library',
      icon: IconUpload,
      action: openUploadDialog,
      variant: 'default'
    },
    {
      id: 'search',
      title: 'Smart Search',
      description: 'Find documents with AI',
      icon: IconSearch,
      action: () => router.push(`/${tenantId}/search`)
    },
    {
      id: 'agents',
      title: 'AI Agents',
      description: 'Chat with your documents',
      icon: IconRobot,
      action: () => router.push(`/${tenantId}/agents`)
    },
    {
      id: 'team',
      title: 'Manage Team',
      description: 'Invite collaborators',
      icon: IconUsers,
      action: () => router.push(`/${tenantId}/settings/team`)
    },
    {
      id: 'templates',
      title: 'Templates',
      description: 'Document templates',
      icon: IconFileText,
      action: () => router.push(`/${tenantId}/templates`)
    },
    {
      id: 'folders',
      title: 'Organize',
      description: 'Create folders',
      icon: IconFolderPlus,
      action: () => router.push(`/${tenantId}/documents`)
    },
    {
      id: 'analytics',
      title: 'Analytics',
      description: 'Usage insights',
      icon: IconChartBar,
      action: () => router.push(`/${tenantId}/analytics`)
    },
    {
      id: 'settings',
      title: 'Settings',
      description: 'Configure workspace',
      icon: IconSettings,
      action: () => router.push(`/${tenantId}/settings`)
    }
  ]

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>Quick Actions</CardTitle>
        <CardDescription>Common tasks and shortcuts</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 @lg:grid-cols-3 @2xl:grid-cols-4">
          {actions.map((action) => {
            const Icon = action.icon
            return (
              <Button
                key={action.id}
                variant={action.variant || 'outline'}
                className="h-auto flex-col gap-2 p-4"
                onClick={action.action}
              >
                <Icon className="h-5 w-5" />
                <div className="text-center">
                  <div className="font-medium text-sm">{action.title}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {action.description}
                  </div>
                </div>
              </Button>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}