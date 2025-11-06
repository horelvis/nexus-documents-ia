'use client'

import { useEffect, useState } from 'react'
import { useUser } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function SimpleOnboardingPage() {
  const { user: clerkUser, isLoaded } = useUser()
  const router = useRouter()
  const [status, setStatus] = useState<'loading' | 'creating' | 'success' | 'error'>('loading')
  const [errorMessage, setErrorMessage] = useState('')
  const [userData, setUserData] = useState<any>(null)

  useEffect(() => {
    if (!isLoaded) return
    
    if (!clerkUser) {
      router.push('/auth/sign-up?plan=free')
      return
    }

    createUser()
  }, [isLoaded, clerkUser])

  const createUser = async () => {
    if (!clerkUser) return
    
    setStatus('creating')
    
    try {
      const response = await fetch('http://192.168.1.37:8000/api/v1/simple-auth/create-or-sync-user', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          clerk_user_id: clerkUser.id,
          email: clerkUser.emailAddresses[0]?.emailAddress || '',
          full_name: clerkUser.fullName || clerkUser.firstName || 'User'
        })
      })

      if (!response.ok) {
        throw new Error(`Error ${response.status}: ${response.statusText}`)
      }

      const data = await response.json()
      
      if (data.success) {
        setUserData(data.user)
        setStatus('success')
        
        // Redirect to dashboard after 2 seconds
        setTimeout(() => {
          window.location.href = `/${data.user.tenant_id}/dashboard`
        }, 2000)
      } else {
        throw new Error('Failed to create user')
      }
    } catch (error) {
      console.error('Error creating user:', error)
      setErrorMessage(error instanceof Error ? error.message : 'Unknown error')
      setStatus('error')
    }
  }

  if (status === 'loading' || status === 'creating') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin mx-auto" />
          <p className="text-muted-foreground">
            {status === 'loading' ? 'Cargando...' : 'Creando tu cuenta...'}
          </p>
        </div>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4 max-w-md">
          <h2 className="text-2xl font-bold text-red-600">Error</h2>
          <p className="text-muted-foreground">{errorMessage}</p>
          <Button onClick={() => createUser()}>Reintentar</Button>
          <Button variant="outline" onClick={() => router.push('/pricing')}>
            Volver a Pricing
          </Button>
        </div>
      </div>
    )
  }

  if (status === 'success') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <h2 className="text-2xl font-bold text-green-600">¡Cuenta creada!</h2>
          <p className="text-muted-foreground">
            Redirigiendo al dashboard...
          </p>
          <Loader2 className="h-6 w-6 animate-spin mx-auto" />
        </div>
      </div>
    )
  }

  return null
}