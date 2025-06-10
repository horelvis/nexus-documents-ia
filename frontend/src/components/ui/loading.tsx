import { IconLoader2 } from "@tabler/icons-react"
import { cn } from "@/lib/utils"

// Company Logo Component
function CompanyLogo({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center justify-center", className)}>
      <div className="bg-gradient-to-br from-blue-600 to-purple-600 text-white rounded-lg p-2">
        <span className="font-bold text-xl">N</span>
      </div>
    </div>
  )
}

interface LoadingProps {
  className?: string
  size?: "sm" | "md" | "lg"
  text?: string
  showLogo?: boolean
}

const sizeClasses = {
  sm: "h-4 w-4",
  md: "h-6 w-6", 
  lg: "h-8 w-8"
}

export function Loading({ className, size = "md", text, showLogo = false }: LoadingProps) {
  if (showLogo) {
    return (
      <div className={cn("flex flex-col items-center justify-center gap-4", className)}>
        <CompanyLogo />
        <div className="flex items-center gap-2">
          <IconLoader2 className={cn("animate-spin", sizeClasses[size])} />
          {text && <span className="text-sm text-muted-foreground">{text}</span>}
        </div>
      </div>
    )
  }

  return (
    <div className={cn("flex items-center justify-center gap-2", className)}>
      <IconLoader2 className={cn("animate-spin", sizeClasses[size])} />
      {text && <span className="text-sm text-muted-foreground">{text}</span>}
    </div>
  )
}

export function PageLoading({ text = "Loading..." }: { text?: string }) {
  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        <div className="min-h-96 flex flex-col items-center justify-center gap-6">
          <CompanyLogo className="mb-2" />
          <div className="flex flex-col items-center gap-3">
            <Loading size="lg" />
            <span className="text-sm text-muted-foreground font-medium">Nexus Document System</span>
            {text && <span className="text-xs text-muted-foreground">{text}</span>}
          </div>
        </div>
      </div>
    </div>
  )
}

export function InlineLoading({ text }: { text?: string }) {
  return (
    <div className="flex items-center justify-center py-4">
      <Loading size="sm" text={text} />
    </div>
  )
}