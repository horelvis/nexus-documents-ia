'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { forwardRef, MouseEvent } from 'react'

interface NavLinkProps extends React.ComponentPropsWithoutRef<typeof Link> {
  children: React.ReactNode
  /** Optional callback to trigger page loading state */
  onStartLoading?: () => void
}

export const NavLink = forwardRef<HTMLAnchorElement, NavLinkProps>(
  ({ children, href, onClick, onStartLoading, ...props }, ref) => {
    const router = useRouter()

    const handleClick = (e: MouseEvent<HTMLAnchorElement>) => {
      // Don't show loader for same page navigation or hash links
      const currentPath = window.location.pathname
      const targetPath = typeof href === 'string' ? href : href.pathname

      if (targetPath && !targetPath.startsWith('#') && targetPath !== currentPath) {
        onStartLoading?.()
      }

      // Call original onClick if provided
      if (onClick) {
        onClick(e)
      }

      // Handle programmatic navigation
      if (e.defaultPrevented) {
        return
      }

      // For external links, don't show loader
      if (typeof href === 'string' && (href.startsWith('http') || href.startsWith('//'))) {
        return
      }
    }

    return (
      <Link ref={ref} href={href} onClick={handleClick} {...props}>
        {children}
      </Link>
    )
  }
)

NavLink.displayName = 'NavLink'