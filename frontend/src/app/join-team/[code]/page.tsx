"use client"

import { useState, useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { apiClient } from '@/lib/api-client'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Loader2, Users, AlertCircle } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import Link from 'next/link'

interface TeamInvitationInfo {
  tenant_id: string
  tenant_name: string
  expires_at: string
  used: boolean
  email?: string
}

export default function JoinTeamPage() {
  const router = useRouter()
  const params = useParams<{ code: string }>()
  const code = params.code
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [invitationInfo, setInvitationInfo] = useState<TeamInvitationInfo | null>(null)

  useEffect(() => {
    checkInvitation()
  }, [code])

  const checkInvitation = async () => {
    setLoading(true)
    setError(null)

    try {
      // First, get invitation info
      const response = await apiClient.get<TeamInvitationInfo>(`/teams/invitations/${code}/info`)
      
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setInvitationInfo(response.data)
      }
    } catch (err) {
      setError('Invalid or expired invitation link')
    } finally {
      setLoading(false)
    }
  }

  const handleJoinTeam = () => {
    if (invitationInfo) {
      // Redirect to sign-up with invitation code
      router.push(`/auth/sign-up?invitation=${code}&tenant=${invitationInfo.tenant_id}`)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-destructive" />
              Invalid Invitation
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
            <div className="mt-4">
              <Link href="/">
                <Button variant="outline" className="w-full">
                  Go to Home
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!invitationInfo) {
    return null
  }

  const isExpired = new Date(invitationInfo.expires_at) < new Date()

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-gradient-to-br from-background to-muted">
      <Card className="max-w-md w-full">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
            <Users className="h-6 w-6 text-primary" />
          </div>
          <CardTitle className="text-2xl">Join {invitationInfo.tenant_name}</CardTitle>
          <CardDescription>
            You've been invited to join the team
            {invitationInfo.email && (
              <span className="block mt-1 font-medium">
                Invitation for: {invitationInfo.email}
              </span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {isExpired ? (
            <>
              <Alert variant="destructive">
                <AlertDescription>
                  This invitation has expired. Please request a new invitation from your team administrator.
                </AlertDescription>
              </Alert>
              <Link href="/">
                <Button variant="outline" className="w-full">
                  Go to Home
                </Button>
              </Link>
            </>
          ) : invitationInfo.used ? (
            <>
              <Alert>
                <AlertDescription>
                  This invitation has already been used. If you need access, please contact your team administrator.
                </AlertDescription>
              </Alert>
              <Link href="/auth/sign-in">
                <Button className="w-full">
                  Sign In
                </Button>
              </Link>
            </>
          ) : (
            <>
              <div className="text-sm text-muted-foreground text-center">
                <p>Click below to create your account and join the team.</p>
                <p className="mt-2">
                  Expires: {new Date(invitationInfo.expires_at).toLocaleDateString()}
                </p>
              </div>
              <Button 
                onClick={handleJoinTeam}
                className="w-full"
                size="lg"
              >
                Accept Invitation
              </Button>
              <div className="text-center text-sm text-muted-foreground">
                Already have an account?{' '}
                <Link href="/auth/sign-in" className="text-primary hover:underline">
                  Sign in
                </Link>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}