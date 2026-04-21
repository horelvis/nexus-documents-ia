"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { IconAlertTriangle, IconHome, IconRefresh, IconMail } from "@tabler/icons-react"
import { useRouter } from "next/navigation"
import { useAuth, useUser } from "@clerk/nextjs"

interface TenantNotFoundProps {
  onRetry?: () => void
}

export function TenantNotFound({ onRetry }: TenantNotFoundProps) {
  const router = useRouter()
  const { signOut } = useAuth()
  const { user } = useUser()

  const handleSignOut = () => {
    signOut(() => {
      router.push('/')
    })
  }

  const handleRetry = () => {
    if (onRetry) {
      onRetry()
    } else {
      window.location.reload()
    }
  }

  const handleContactSupport = () => {
    const subject = encodeURIComponent(`Tenant Access Issue - User: ${user?.emailAddresses[0]?.emailAddress}`)
    const body = encodeURIComponent(`
Hi Support Team,

I'm experiencing an issue accessing my tenant organization. Here are the details:

- User Email: ${user?.emailAddresses[0]?.emailAddress}
- Error: Organization setup issue detected
- Time: ${new Date().toISOString()}

Please help me resolve this issue.

Thank you!
    `)
    
    window.open(`mailto:support@nouxcube.com?subject=${subject}&body=${body}`)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mb-4">
            <IconAlertTriangle className="w-6 h-6 text-red-600" />
          </div>
          <CardTitle className="text-xl font-semibold">Tenant Not Found</CardTitle>
          <CardDescription className="text-sm">
            There's an issue with your organization setup. This usually happens when:
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-sm text-muted-foreground space-y-2">
            <div className="flex items-start gap-2">
              <span className="w-1 h-1 bg-gray-400 rounded-full mt-2 flex-shrink-0"></span>
              <span>Your account hasn't been properly set up</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="w-1 h-1 bg-gray-400 rounded-full mt-2 flex-shrink-0"></span>
              <span>There's a configuration issue on our end</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="w-1 h-1 bg-gray-400 rounded-full mt-2 flex-shrink-0"></span>
              <span>Your organization has been deactivated</span>
            </div>
          </div>

          <div className="space-y-2">
            <Button onClick={handleRetry} className="w-full" variant="default">
              <IconRefresh className="w-4 h-4 mr-2" />
              Try Again
            </Button>
            
            <Button onClick={handleContactSupport} className="w-full" variant="outline">
              <IconMail className="w-4 h-4 mr-2" />
              Contact Support
            </Button>
            
            <Button onClick={handleSignOut} className="w-full" variant="ghost">
              <IconHome className="w-4 h-4 mr-2" />
              Sign Out & Go Home
            </Button>
          </div>
          
          <div className="text-center">
            <p className="text-xs text-muted-foreground">
              If this problem persists, please contact our support team.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}