'use client'

/**
 * Shared User Menu Component
 *
 * Base user menu that can be used by both SaaS (with Clerk) and
 * On-premise (with OIDC/KeyCloak) deployments.
 *
 * Features:
 * - User profile display
 * - Theme toggle (light/dark/system)
 * - Navigation items
 * - Logout action
 */

import { useState, useEffect, type ReactNode } from 'react'
import {
  User,
  Settings,
  LogOut,
  Moon,
  Sun,
  Monitor,
  Keyboard,
  HelpCircle,
  Building2,
} from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
  DropdownMenuShortcut,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from './dropdown-menu'
import { Avatar, AvatarFallback, AvatarImage } from './avatar'
import { Button } from './button'
import { Badge } from './badge'
import { cn } from '@/lib/utils'

type Theme = 'light' | 'dark' | 'system'

export interface UserMenuUser {
  id: string
  email?: string
  fullName?: string
  avatarUrl?: string
  tenantId?: string
  planName?: string
}

export interface UserMenuNavItem {
  label: string
  href: string
  icon?: ReactNode
  shortcut?: string
}

export interface UserMenuProps {
  /** User data to display */
  user: UserMenuUser | null
  /** Navigation items to show in the menu */
  navItems?: UserMenuNavItem[]
  /** Called when logout is clicked */
  onLogout?: () => void
  /** Called when a nav item is clicked (for SPA navigation) */
  onNavigate?: (href: string) => void
  /** Show theme toggle */
  showThemeToggle?: boolean
  /** Show keyboard shortcuts */
  showKeyboardShortcuts?: boolean
  /** Custom keyboard shortcuts to display */
  keyboardShortcuts?: Array<{ label: string; shortcut: string }>
  /** Additional class name */
  className?: string
  /** Children to render inside the trigger (for custom trigger) */
  children?: ReactNode
  /** Show help link */
  showHelp?: boolean

  // === Extensibility Slots ===
  /** Custom section rendered after navigation items (e.g., billing, plans) */
  extraNavSection?: ReactNode
  /** Custom section rendered after preferences (e.g., language selector) */
  extraPreferencesSection?: ReactNode
  /** Custom section rendered before logout */
  extraFooterSection?: ReactNode
  /** Custom badge variant for plan */
  planBadgeVariant?: 'default' | 'secondary' | 'destructive' | 'outline'

  // === i18n Support ===
  /** Labels for internationalization */
  labels?: {
    account?: string
    preferences?: string
    theme?: string
    themeLight?: string
    themeDark?: string
    themeSystem?: string
    keyboardShortcuts?: string
    help?: string
    logout?: string
    user?: string
  }
}

/**
 * Get user initials from name or email
 */
function getUserInitials(user: UserMenuUser | null): string {
  if (!user) return 'U'

  if (user.fullName) {
    return user.fullName
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  if (user.email) {
    return user.email.slice(0, 2).toUpperCase()
  }

  return 'U'
}

/**
 * Theme management helpers
 */
function getStoredTheme(): Theme {
  if (typeof window === 'undefined') return 'system'
  return (localStorage.getItem('theme') as Theme) || 'system'
}

function applyTheme(theme: Theme): void {
  if (typeof window === 'undefined') return

  const root = document.documentElement
  if (theme === 'system') {
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    root.classList.toggle('dark', systemDark)
  } else {
    root.classList.toggle('dark', theme === 'dark')
  }
}

const DEFAULT_SHORTCUTS = [
  { label: 'Nueva consulta', shortcut: '⌘ N' },
  { label: 'Buscar', shortcut: '⌘ K' },
  { label: 'Configuración', shortcut: '⇧ S' },
]

// Default labels (Spanish)
const DEFAULT_LABELS = {
  account: 'Cuenta',
  preferences: 'Preferencias',
  theme: 'Tema',
  themeLight: 'Claro',
  themeDark: 'Oscuro',
  themeSystem: 'Sistema',
  keyboardShortcuts: 'Atajos de teclado',
  help: 'Ayuda y soporte',
  logout: 'Cerrar sesión',
  user: 'Usuario',
}

export function UserMenu({
  user,
  navItems = [],
  onLogout,
  onNavigate,
  showThemeToggle = true,
  showKeyboardShortcuts = true,
  keyboardShortcuts = DEFAULT_SHORTCUTS,
  className,
  children,
  showHelp = true,
  extraNavSection,
  extraPreferencesSection,
  extraFooterSection,
  planBadgeVariant = 'secondary',
  labels: customLabels,
}: UserMenuProps) {
  // Merge custom labels with defaults
  const labels = { ...DEFAULT_LABELS, ...customLabels }
  const [theme, setTheme] = useState<Theme>('system')

  // Initialize theme
  useEffect(() => {
    const stored = getStoredTheme()
    setTheme(stored)
    applyTheme(stored)
  }, [])

  const handleThemeChange = (newTheme: Theme) => {
    setTheme(newTheme)
    localStorage.setItem('theme', newTheme)
    applyTheme(newTheme)
  }

  const handleNavClick = (href: string) => {
    if (onNavigate) {
      onNavigate(href)
    } else {
      window.location.href = href
    }
  }

  const userInitials = getUserInitials(user)
  const ThemeIcon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {children || (
          <Button
            variant="ghost"
            className={cn(
              'relative h-10 w-10 rounded-full p-0',
              'ring-2 ring-transparent hover:ring-primary/30',
              'focus-visible:ring-2 focus-visible:ring-primary',
              'transition-all duration-200',
              className
            )}
          >
            <Avatar className="h-10 w-10">
              {user?.avatarUrl && <AvatarImage src={user.avatarUrl} alt={user.fullName || 'User'} />}
              <AvatarFallback className="bg-gradient-to-br from-primary via-primary/80 to-primary/60 text-primary-foreground text-sm font-semibold">
                {userInitials}
              </AvatarFallback>
            </Avatar>
          </Button>
        )}
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-80" sideOffset={8}>
        {/* User Profile Header */}
        {user && (
          <>
            <div className="p-4 bg-gradient-to-br from-muted/50 to-muted/30 rounded-t-md -m-1 mb-1">
              <div className="flex items-start gap-4">
                <Avatar className="h-14 w-14 ring-2 ring-background shadow-lg">
                  {user.avatarUrl && <AvatarImage src={user.avatarUrl} alt={user.fullName || 'User'} />}
                  <AvatarFallback className="bg-gradient-to-br from-primary via-primary/80 to-primary/60 text-primary-foreground text-lg font-bold">
                    {userInitials}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold truncate">{user.fullName || 'Usuario'}</p>
                    {user.planName && (
                      <Badge variant={planBadgeVariant} className="text-[10px] px-1.5 py-0 h-4">
                        {user.planName}
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground truncate">{user.email}</p>
                  {user.tenantId && (
                    <div className="flex items-center gap-1.5 pt-1">
                      <Building2 className="h-3 w-3 text-muted-foreground" />
                      <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
                        {user.tenantId.slice(0, 8)}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
            <DropdownMenuSeparator className="my-1" />
          </>
        )}

        {/* Navigation Items */}
        {navItems.length > 0 && (
          <>
            <DropdownMenuGroup>
              <DropdownMenuLabel className="text-xs text-muted-foreground font-normal px-2">
                {labels.account}
              </DropdownMenuLabel>
              {navItems.map((item) => (
                <DropdownMenuItem
                  key={item.href}
                  className="cursor-pointer"
                  onClick={() => handleNavClick(item.href)}
                >
                  {item.icon || <User className="mr-3 h-4 w-4 text-muted-foreground" />}
                  {item.label}
                  {item.shortcut && <DropdownMenuShortcut>{item.shortcut}</DropdownMenuShortcut>}
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
            <DropdownMenuSeparator className="my-1" />
          </>
        )}

        {/* Extra Navigation Section (slot) */}
        {extraNavSection && (
          <>
            {extraNavSection}
            <DropdownMenuSeparator className="my-1" />
          </>
        )}

        {/* Preferences */}
        {(showThemeToggle || showKeyboardShortcuts || extraPreferencesSection) && (
          <>
            <DropdownMenuGroup>
              <DropdownMenuLabel className="text-xs text-muted-foreground font-normal px-2">
                {labels.preferences}
              </DropdownMenuLabel>

              {/* Theme Submenu */}
              {showThemeToggle && (
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger className="cursor-pointer">
                    <ThemeIcon className="mr-3 h-4 w-4 text-muted-foreground" />
                    {labels.theme}
                    <span className="ml-auto text-xs text-muted-foreground capitalize">
                      {theme === 'system' ? labels.themeSystem : theme === 'dark' ? labels.themeDark : labels.themeLight}
                    </span>
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent className="w-40">
                    <DropdownMenuRadioGroup value={theme} onValueChange={(v) => handleThemeChange(v as Theme)}>
                      <DropdownMenuRadioItem value="light" className="cursor-pointer">
                        <Sun className="mr-2 h-4 w-4" />
                        {labels.themeLight}
                      </DropdownMenuRadioItem>
                      <DropdownMenuRadioItem value="dark" className="cursor-pointer">
                        <Moon className="mr-2 h-4 w-4" />
                        {labels.themeDark}
                      </DropdownMenuRadioItem>
                      <DropdownMenuRadioItem value="system" className="cursor-pointer">
                        <Monitor className="mr-2 h-4 w-4" />
                        {labels.themeSystem}
                      </DropdownMenuRadioItem>
                    </DropdownMenuRadioGroup>
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
              )}

              {/* Keyboard Shortcuts */}
              {showKeyboardShortcuts && keyboardShortcuts.length > 0 && (
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger className="cursor-pointer">
                    <Keyboard className="mr-3 h-4 w-4 text-muted-foreground" />
                    {labels.keyboardShortcuts}
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent className="w-56">
                    <div className="p-2 space-y-2">
                      {keyboardShortcuts.map((shortcut) => (
                        <div key={shortcut.label} className="flex justify-between text-xs">
                          <span className="text-muted-foreground">{shortcut.label}</span>
                          <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono">
                            {shortcut.shortcut}
                          </kbd>
                        </div>
                      ))}
                    </div>
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
              )}

              {/* Extra Preferences Section (slot) */}
              {extraPreferencesSection}
            </DropdownMenuGroup>
            <DropdownMenuSeparator className="my-1" />
          </>
        )}

        {/* Help */}
        {showHelp && (
          <DropdownMenuItem className="cursor-pointer" onClick={() => handleNavClick('/help')}>
            <HelpCircle className="mr-3 h-4 w-4 text-muted-foreground" />
            {labels.help}
          </DropdownMenuItem>
        )}

        {/* Extra Footer Section (slot) */}
        {extraFooterSection}

        <DropdownMenuSeparator className="my-1" />

        {/* Logout */}
        {onLogout && (
          <DropdownMenuItem
            onClick={onLogout}
            className="cursor-pointer text-destructive focus:text-destructive focus:bg-destructive/10"
          >
            <LogOut className="mr-3 h-4 w-4" />
            {labels.logout}
            <DropdownMenuShortcut>⇧Q</DropdownMenuShortcut>
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
