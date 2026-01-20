"use client"

import { usePathname } from "next/navigation"

export function useActiveRoute() {
  const pathname = usePathname()

  const isActive = (href: string) => {
    if (href === "/dashboard") {
      return pathname === "/dashboard"
    }
    return pathname.startsWith(href)
  }

  const isExactActive = (href: string) => {
    return pathname === href
  }

  return {
    pathname,
    isActive,
    isExactActive
  }
}