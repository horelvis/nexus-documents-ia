import { UnifiedLoader, InlineLoader as UnifiedInlineLoader } from "./unified-loader"

interface LoadingProps {
  className?: string
  size?: "sm" | "md" | "lg"
  text?: string
  showLogo?: boolean
}

// Backwards compatibility wrapper for existing Loading component
export function Loading({ className, size = "md", text, showLogo = false }: LoadingProps) {
  return (
    <UnifiedLoader
      variant="inline"
      size={size}
      text={text}
      showLogo={showLogo}
      className={className}
      fullScreen={false}
    />
  )
}

export function PageLoading({ text = "Loading..." }: { text?: string }) {
  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        <div className="min-h-96">
          <UnifiedLoader
            variant="page"
            size="lg"
            text={text}
            subtext="Nexus Document System"
            showLogo={true}
            fullScreen={false}
          />
        </div>
      </div>
    </div>
  )
}

export function InlineLoading({ text }: { text?: string }) {
  return <UnifiedInlineLoader text={text} />
}