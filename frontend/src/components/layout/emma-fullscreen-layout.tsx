"use client"

/**
 * Emma Fullscreen Layout
 *
 * Minimal layout for on-premise Emma-centric deployment.
 * Emma chat occupies the full screen with a minimal header.
 *
 * Used when Feature.EMMA_FULLSCREEN_MODE is enabled (default for on-premise).
 */

import { ReactNode } from "react"
import Link from "next/link"
import { Brain, Plug, Settings, LogOut } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { useUserContext } from "@/contexts/user-context"
import { cn } from "@/lib/utils"

interface EmmaFullscreenLayoutProps {
  children: ReactNode
  tenantId: string
  className?: string
}

export function EmmaFullscreenLayout({
  children,
  tenantId,
  className,
}: EmmaFullscreenLayoutProps) {
  const { backendUser, handleLogout } = useUserContext()

  const userInitials = backendUser?.full_name
    ? backendUser.full_name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : backendUser?.email?.slice(0, 2).toUpperCase() || "U"

  return (
    <div className={cn("flex flex-col h-screen bg-background", className)}>
      {/* Minimal Header */}
      <header className="h-14 border-b flex items-center justify-between px-4 shrink-0">
        {/* Logo and Brand */}
        <Link
          href={`/${tenantId}/emma`}
          className="flex items-center gap-3 hover:opacity-80 transition-opacity"
        >
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10">
            <Brain className="h-5 w-5 text-primary" />
          </div>
          <span className="font-semibold text-lg">Emma</span>
        </Link>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {/* Connectors */}
          <Button variant="ghost" size="icon" asChild title="Conectores">
            <Link href={`/${tenantId}/connectors`}>
              <Plug className="h-5 w-5" />
            </Link>
          </Button>

          {/* Settings */}
          <Button variant="ghost" size="icon" asChild title="Configuración">
            <Link href={`/${tenantId}/settings`}>
              <Settings className="h-5 w-5" />
            </Link>
          </Button>

          {/* User Menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="relative h-9 w-9 rounded-full"
              >
                <Avatar className="h-9 w-9">
                  <AvatarImage
                    src={backendUser?.profile_image_url || undefined}
                    alt={backendUser?.full_name || "User"}
                  />
                  <AvatarFallback className="bg-primary/10 text-primary text-sm">
                    {userInitials}
                  </AvatarFallback>
                </Avatar>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel>
                <div className="flex flex-col space-y-1">
                  <p className="text-sm font-medium">
                    {backendUser?.full_name || "Usuario"}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {backendUser?.email}
                  </p>
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href={`/${tenantId}/settings/profile`}>
                  <Settings className="mr-2 h-4 w-4" />
                  Configuración
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={handleLogout}
                className="text-red-600 focus:text-red-600"
              >
                <LogOut className="mr-2 h-4 w-4" />
                Cerrar sesión
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {/* Main Content - Emma fills everything */}
      <main className="flex-1 min-h-0 overflow-hidden">{children}</main>
    </div>
  )
}

/**
 * Simple version without user context for SSO mode
 * where we manage auth differently
 */
export function EmmaFullscreenLayoutSimple({
  children,
  tenantId,
  user,
  onLogout,
  className,
}: {
  children: ReactNode
  tenantId: string
  user?: { name?: string; email?: string; picture?: string }
  onLogout?: () => void
  className?: string
}) {
  const userInitials = user?.name
    ? user.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : user?.email?.slice(0, 2).toUpperCase() || "U"

  return (
    <div className={cn("flex flex-col h-screen bg-background", className)}>
      {/* Minimal Header */}
      <header className="h-14 border-b flex items-center justify-between px-4 shrink-0">
        <Link
          href={`/${tenantId}/emma`}
          className="flex items-center gap-3 hover:opacity-80 transition-opacity"
        >
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10">
            <Brain className="h-5 w-5 text-primary" />
          </div>
          <span className="font-semibold text-lg">Emma</span>
        </Link>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" asChild title="Conectores">
            <Link href={`/${tenantId}/connectors`}>
              <Plug className="h-5 w-5" />
            </Link>
          </Button>

          <Button variant="ghost" size="icon" asChild title="Configuración">
            <Link href={`/${tenantId}/settings`}>
              <Settings className="h-5 w-5" />
            </Link>
          </Button>

          {user && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="relative h-9 w-9 rounded-full"
                >
                  <Avatar className="h-9 w-9">
                    <AvatarImage src={user.picture} alt={user.name || "User"} />
                    <AvatarFallback className="bg-primary/10 text-primary text-sm">
                      {userInitials}
                    </AvatarFallback>
                  </Avatar>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>
                  <div className="flex flex-col space-y-1">
                    <p className="text-sm font-medium">{user.name || "Usuario"}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {user.email}
                    </p>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                {onLogout && (
                  <DropdownMenuItem
                    onClick={onLogout}
                    className="text-red-600 focus:text-red-600"
                  >
                    <LogOut className="mr-2 h-4 w-4" />
                    Cerrar sesión
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </header>

      <main className="flex-1 min-h-0 overflow-hidden">{children}</main>
    </div>
  )
}
