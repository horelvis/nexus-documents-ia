"use client"

import { IconLoader2 } from "@tabler/icons-react"
import { cn } from "../lib/utils"
import { useEffect, useState } from "react"

// Company Logo Component (perfectamente circular)
function CompanyLogo({ className, size = "md" }: { className?: string; size?: "sm" | "md" | "lg" }) {
  const sizeClasses = {
    sm: "w-8 h-8 text-sm",
    md: "w-10 h-10 text-base", 
    lg: "w-12 h-12 text-lg"
  }
  
  return (
    <div className={cn("flex items-center justify-center", className)}>
      <div className={cn(
        "bg-gradient-to-br from-purple-500 via-purple-600 to-purple-700",
        "dark:from-purple-400 dark:via-purple-500 dark:to-purple-600",
        "text-white rounded-full shadow-xl font-bold",
        "border-2 border-white/20 dark:border-white/10",
        "transition-all duration-300",
        "hover:scale-110 hover:shadow-2xl",
        "relative overflow-hidden",
        "flex items-center justify-center",
        sizeClasses[size]
      )}>
        {/* Efecto de brillo */}
        <div className="absolute inset-0 bg-gradient-to-tr from-white/20 via-transparent to-transparent rounded-full" />
        <span className="relative z-10 font-extrabold tracking-tight">N</span>
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
    <div className="relative flex items-center justify-center">
      {/* Círculo base */}
      <div className={cn(
        "absolute rounded-full border-4 border-purple-100/50 dark:border-purple-900/50",
        sizeClasses[size]
      )} />
      
      {/* Círculo principal que gira */}
      <div className={cn(
        "absolute animate-spin rounded-full border-4 border-transparent",
        "border-t-purple-600 border-r-purple-500 border-l-purple-400",
        "dark:border-t-purple-400 dark:border-r-purple-300 dark:border-l-purple-500",
        "drop-shadow-lg",
        sizeClasses[size]
      )} />
      
      {/* Círculo secundario que gira en dirección opuesta */}
      <div className={cn(
        "absolute animate-reverse-spin rounded-full border-2 border-transparent",
        "border-b-purple-400 border-l-purple-300",
        "dark:border-b-purple-600 dark:border-l-purple-700",
        sizeClasses[size]
      )} />
      
      {/* Logo en el centro (no gira) con mejores efectos */}
      {showLogo && (variant === "initial" || variant === "page") && (
        <div className="relative z-10 animate-pulse">
          <CompanyLogo 
            size={size === "lg" ? "md" : size === "md" ? "sm" : "sm"} 
            className="drop-shadow-md"
          />
        </div>
      )}
      
      {/* Efecto glow para variantes principales - perfectamente circular */}
      {(variant === "initial" || variant === "page") && size !== "sm" && (
        <>
          <div className={cn(
            "absolute animate-ping rounded-full bg-purple-500/20 dark:bg-purple-400/20",
            size === "lg" ? "w-20 h-20" : size === "md" ? "w-14 h-14" : "w-8 h-8"
          )} />
          <div className={cn(
            "absolute animate-pulse rounded-full bg-gradient-to-r from-purple-500/10 to-purple-600/10",
            "dark:from-purple-400/10 dark:to-purple-500/10",
            size === "lg" ? "w-24 h-24" : size === "md" ? "w-16 h-16" : "w-10 h-10"
          )} />
        </>
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
      <div className={cn("flex items-center justify-center gap-3 py-4", className)}>
        <div className="relative flex items-center justify-center">
          <div className="absolute w-4 h-4 rounded-full border-2 border-purple-200 dark:border-purple-900" />
          <div className="absolute w-4 h-4 animate-spin rounded-full border-2 border-transparent border-t-purple-600 dark:border-t-purple-400" />
        </div>
        {text && <span className="text-sm text-muted-foreground">{text}</span>}
      </div>
    )
  }

  // Contenido del loader para variantes initial y page
  const LoaderContent = (
    <div className="flex flex-col items-center space-y-6">
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