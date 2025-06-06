"use client"

import { UserButton as ClerkUserButton, useUser } from '@clerk/nextjs'

export function UserButton() {
  const { isLoaded, isSignedIn, user } = useUser()

  if (!isLoaded || !isSignedIn) {
    return null
  }

  return (
    <ClerkUserButton 
      afterSignOutUrl="/"
      appearance={{
        elements: {
          avatarBox: "h-8 w-8"
        }
      }}
    />
  )
}