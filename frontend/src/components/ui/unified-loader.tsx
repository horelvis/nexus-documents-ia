"use client"

import { IconLoader2 } from "@tabler/icons-react"
import { cn } from "@/lib/utils"
import { useEffect, useState } from "react"

// Company Logo Component (reutilizado del loading.tsx)
function CompanyLogo({ className, size = "md" }: { className?: string; size?: "sm" | "md" | "lg" }) {
  const sizeClasses = {
    sm: "p-1.5 text-lg",
    md: "p-2 text-xl",
    lg: "p-3 text-2xl"
  }
  
  return (
    <div className={cn("flex items-center justify-center", className)}>
      <div className={cn(
        "bg-gradient-to-br from-blue-600 to-purple-600 dark:from-blue-500 dark:to-purple-500",
        "text-white rounded-lg shadow-lg font-bold",
        sizeClasses[size]
      )}>
        N
      </div>
    </div>
  )
}

interface UnifiedLoaderProps {
  variant?: "initial" | "page" | "inline" | "minimal"
  size?: "sm" | "md" | "lg"
  text?: string
  subtext?: string
  showLogo?: boolean
  className?: string
  fullScreen?: boolean
}

const sizeClasses = {
  sm: "h-6 w-6",
  md: "h-12 w-12",
  lg: "h-16 w-16"
}

export function UnifiedLoader({
  variant = "page",
  size = "md",
  text,
  subtext,
  showLogo = true,
  className,
  fullScreen = true
}: UnifiedLoaderProps) {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) return null

  // Componente principal del spinner con animaciones mejoradas
  const SpinnerComponent = (
    <div className="relative">
      <IconLoader2 
        className={cn(
          "animate-spin text-purple-600 dark:text-purple-400",
          sizeClasses[size]
        )} 
      />
      {(variant === "initial" || variant === "page") && size !== "sm" && (
        <div className={cn(
          "absolute inset-0 animate-ping rounded-full bg-purple-600/20 dark:bg-purple-400/20",
          sizeClasses[size]
        )} />
      )}
    </div>
  )

  // Variante minimal - solo spinner, sin contenedor
  if (variant === "minimal") {
    return SpinnerComponent
  }

  // Variante inline - para uso dentro de componentes
  if (variant === "inline") {
    return (
      <div className={cn("flex items-center justify-center gap-2 py-4", className)}>
        <IconLoader2 className="h-4 w-4 animate-spin text-purple-600 dark:text-purple-400" />
        {text && <span className="text-sm text-muted-foreground">{text}</span>}
      </div>
    )
  }

  // Contenido del loader para variantes initial y page
  const LoaderContent = (
    <div className="flex flex-col items-center space-y-4">
      {showLogo && variant === "initial" && (
        <CompanyLogo size={size} className="mb-2" />
      )}
      
      {SpinnerComponent}
      
      <div className="space-y-2 text-center">
        {(showLogo && variant === "page") && (
          <p className="text-sm font-semibold text-purple-600 dark:text-purple-400">
            Nexus Document System
          </p>
        )}
        {text && (
          <p className={cn(
            "font-medium",
            variant === "initial" ? "text-base" : "text-sm"
          )}>
            {text}
          </p>
        )}
        {subtext && (
          <p className="text-xs text-muted-foreground">
            {subtext}
          </p>
        )}
      </div>
    </div>
  )

  // Para loaders de pantalla completa
  if (fullScreen) {
    return (
      <div 
        className={cn(
          "fixed inset-0 z-[100]",
          variant === "page" && "bg-background/80 backdrop-blur-sm animate-in fade-in duration-200",
          variant === "initial" && "bg-background",
          className
        )}
      >
        <div className="fixed left-[50%] top-[50%] -translate-x-[50%] -translate-y-[50%]">
          {LoaderContent}
        </div>
      </div>
    )
  }

  // Para loaders no fullscreen
  return (
    <div className={cn("flex items-center justify-center", className)}>
      {LoaderContent}
    </div>
  )
}

// Componente de barra de progreso superior (para navegación)
interface TopProgressBarProps {
  isLoading: boolean
  progress: number
  className?: string
}

export function TopProgressBar({ isLoading, progress, className }: TopProgressBarProps) {
  if (!isLoading) return null

  return (
    <div
      className={cn(
        "fixed top-0 left-0 right-0 z-[100] h-1 bg-purple-600/20 dark:bg-purple-400/20",
        className
      )}
    >
      <div
        className="h-full bg-purple-600 dark:bg-purple-400 transition-all duration-300 ease-out"
        style={{
          width: `${progress}%`,
          boxShadow: '0 0 10px currentColor, 0 0 5px currentColor'
        }}
      />
    </div>
  )
}

// Exports convenientes para casos de uso comunes
export const InitialLoader = () => (
  <UnifiedLoader 
    variant="initial" 
    size="lg"
    text="Cargando..."
    showLogo={true}
  />
)

export const PageTransitionLoader = () => (
  <UnifiedLoader 
    variant="page"
    size="md" 
    text="Cargando página..."
    subtext="Por favor espera un momento"
    showLogo={true}
  />
)

export const InlineLoader = ({ text }: { text?: string }) => (
  <UnifiedLoader 
    variant="inline"
    text={text}
    fullScreen={false}
  />
)

export const MinimalSpinner = ({ size = "md" }: { size?: "sm" | "md" | "lg" }) => (
  <UnifiedLoader 
    variant="minimal"
    size={size}
    fullScreen={false}
  />
)