'use client'

/**
 * Emma User Menu Component
 *
 * Wraps the shared UserMenu with Emma-specific configuration.
 * Uses OIDC/KeyCloak authentication context.
 */

import { useRouter } from 'next/navigation'
import { IconUser, IconSettings, IconPlug } from '@tabler/icons-react'
import { UserMenu as SharedUserMenu, type UserMenuNavItem } from '@/components/ui'
import { useAuth } from '@/contexts/auth-context'

interface UserMenuProps {
  className?: string
}

export function UserMenu({ className }: UserMenuProps) {
  const { user, logout } = useAuth()
  const router = useRouter()

  // Navigation items specific to Emma
  const navItems: UserMenuNavItem[] = [
    {
      label: 'Mi perfil',
      href: '/profile',
      icon: <IconUser className="mr-3 h-4 w-4 text-muted-foreground" />,
      shortcut: '⇧P',
    },
    {
      label: 'Conectores',
      href: '/connectors',
      icon: <IconPlug className="mr-3 h-4 w-4 text-muted-foreground" />,
    },
    {
      label: 'Configuración',
      href: '/settings',
      icon: <IconSettings className="mr-3 h-4 w-4 text-muted-foreground" />,
      shortcut: '⇧S',
    },
  ]

  // Keyboard shortcuts for Emma
  const keyboardShortcuts = [
    { label: 'Nueva consulta', shortcut: '⌘ N' },
    { label: 'Buscar documentos', shortcut: '⌘ K' },
    { label: 'Configuración', shortcut: '⇧ S' },
    { label: 'Mi perfil', shortcut: '⇧ P' },
  ]

  // Handle navigation
  const handleNavigate = (href: string) => {
    router.push(href)
  }

  // Map auth context user to UserMenu format
  const userMenuUser = user
    ? {
        id: user.id,
        email: user.email,
        fullName: user.full_name,
        tenantId: user.tenant_id,
        planName: 'Enterprise', // On-premise is always enterprise
      }
    : null

  return (
    <SharedUserMenu
      user={userMenuUser}
      navItems={navItems}
      onLogout={logout}
      onNavigate={handleNavigate}
      showThemeToggle={true}
      showKeyboardShortcuts={true}
      keyboardShortcuts={keyboardShortcuts}
      className={className}
    />
  )
}
