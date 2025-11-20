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
  IconFolderPlus,
  IconArrowRight
} from "@tabler/icons-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { useUpload } from "@/contexts/upload-context"

interface QuickAction {
  id: string
  title: string
  description: string
  icon: any
  action: () => void
  color?: string
  primary?: boolean
}

export function QuickActions({ tenantId }: { tenantId: string }) {
  const router = useRouter()
  const { openUploadDialog } = useUpload()

  const actions: QuickAction[] = [
    {
      id: 'upload',
      title: 'Upload',
      description: 'Add files',
      icon: IconUpload,
      action: openUploadDialog,
      color: 'blue',
      primary: true
    },
    {
      id: 'search',
      title: 'Search',
      description: 'Find docs',
      icon: IconSearch,
      action: () => router.push(`/${tenantId}/search`),
      color: 'green'
    },
    {
      id: 'agents',
      title: 'AI Chat',
      description: 'Ask AI',
      icon: IconRobot,
      action: () => router.push(`/${tenantId}/chat`),
      color: 'purple'
    },
    {
      id: 'team',
      title: 'Team',
      description: 'Manage',
      icon: IconUsers,
      action: () => router.push(`/${tenantId}/settings/team`),
      color: 'orange'
    },
    {
      id: 'templates',
      title: 'Templates',
      description: 'Use templates',
      icon: IconFileText,
      action: () => router.push(`/${tenantId}/templates`),
      color: 'pink'
    },
    {
      id: 'folders',
      title: 'Organize',
      description: 'Folders',
      icon: IconFolderPlus,
      action: () => router.push(`/${tenantId}/documents`),
      color: 'yellow'
    },
    {
      id: 'analytics',
      title: 'Analytics',
      description: 'View stats',
      icon: IconChartBar,
      action: () => router.push(`/${tenantId}/analytics`),
      color: 'indigo'
    },
    {
      id: 'settings',
      title: 'Settings',
      description: 'Configure',
      icon: IconSettings,
      action: () => router.push(`/${tenantId}/settings`),
      color: 'gray'
    }
  ]

  const colorClasses = {
    blue: 'bg-blue-500/10 hover:bg-blue-500/20 dark:bg-blue-500/10 dark:hover:bg-blue-500/20 text-blue-700 dark:text-blue-400',
    green: 'bg-green-500/10 hover:bg-green-500/20 dark:bg-green-500/10 dark:hover:bg-green-500/20 text-green-700 dark:text-green-400',
    purple: 'bg-purple-500/10 hover:bg-purple-500/20 dark:bg-purple-500/10 dark:hover:bg-purple-500/20 text-purple-700 dark:text-purple-400',
    orange: 'bg-orange-500/10 hover:bg-orange-500/20 dark:bg-orange-500/10 dark:hover:bg-orange-500/20 text-orange-700 dark:text-orange-400',
    pink: 'bg-pink-500/10 hover:bg-pink-500/20 dark:bg-pink-500/10 dark:hover:bg-pink-500/20 text-pink-700 dark:text-pink-400',
    yellow: 'bg-yellow-500/10 hover:bg-yellow-500/20 dark:bg-yellow-500/10 dark:hover:bg-yellow-500/20 text-yellow-700 dark:text-yellow-400',
    indigo: 'bg-indigo-500/10 hover:bg-indigo-500/20 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-indigo-700 dark:text-indigo-400',
    gray: 'bg-gray-500/10 hover:bg-gray-500/20 dark:bg-gray-500/10 dark:hover:bg-gray-500/20 text-gray-700 dark:text-gray-400'
  }

  return (
    <Card className="h-full quick-actions-panel">
      <CardHeader>
        <CardTitle>Quick Actions</CardTitle>
        <CardDescription>Common tasks and shortcuts</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {actions.map((action) => {
            const Icon = action.icon
            const colorClass = action.color ? colorClasses[action.color as keyof typeof colorClasses] : colorClasses.gray
            
            return (
              <button
                key={action.id}
                onClick={action.action}
                className={cn(
                  "group relative flex items-center gap-3 p-3 rounded-lg transition-all duration-200",
                  "border border-border/40 hover:border-border/60",
                  colorClass,
                  action.primary && "ring-1 ring-primary/30"
                )}
              >
                <div className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-lg",
                  "bg-background/50 dark:bg-background/30"
                )}>
                  <Icon className="h-5 w-5" />
                </div>
                
                <div className="flex-1 text-left">
                  <div className="font-semibold text-sm leading-none">
                    {action.title}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {action.description}
                  </div>
                </div>
                
                <IconArrowRight className="h-4 w-4 opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200" />
              </button>
            )
          })}
        </div>
        
        {/* Compact grid for smaller screens */}
        <div className="mt-4 pt-4 border-t sm:hidden">
          <div className="grid grid-cols-4 gap-2">
            {actions.slice(0, 4).map((action) => {
              const Icon = action.icon
              return (
                <button
                  key={`compact-${action.id}`}
                  onClick={action.action}
                  className="flex flex-col items-center gap-1.5 p-2 rounded-lg hover:bg-muted transition-colors"
                >
                  <Icon className="h-5 w-5" />
                  <span className="text-[10px] font-medium">{action.title}</span>
                </button>
              )
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}