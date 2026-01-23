"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { IconUserOff, IconHome, IconRefresh, IconMail, IconUserPlus } from "@tabler/icons-react"
import { useRouter } from "next/navigation"
import { useAuth, useUser } from "@clerk/nextjs"
import { useTranslation } from "@/lib/i18n/hooks"

interface UserNotFoundProps {
  onRetry?: () => void
}

export function UserNotFound({ onRetry }: UserNotFoundProps) {
  const router = useRouter()
  const { signOut } = useAuth()
  const { user } = useUser()
  const { t } = useTranslation()

  const handleSignOut = () => {
    signOut(() => {
      router.push('/')
    })
  }

  const handleReRegister = () => {
    // Sign out and redirect to signup to allow re-registration
    signOut(() => {
      router.push('/auth/sign-up')
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
    const email = user?.emailAddresses[0]?.emailAddress || ''
    const clerkId = user?.id || ''
    const time = new Date().toISOString()

    const subject = encodeURIComponent(
      t('userNotFound.supportEmail.subject') + ` - ${email}`
    )
    const body = encodeURIComponent(
      t('userNotFound.supportEmail.body', { email, clerkId, time })
    )

    window.open(`mailto:support@nouxcube.com?subject=${subject}&body=${body}`)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md border-border bg-card">
        <CardHeader className="text-center">
          <div className="mx-auto w-12 h-12 bg-orange-500/20 rounded-full flex items-center justify-center mb-4">
            <IconUserOff className="w-6 h-6 text-orange-500" />
          </div>
          <CardTitle className="text-xl font-semibold text-foreground">
            {t('userNotFound.title')}
          </CardTitle>
          <CardDescription className="text-sm text-muted-foreground">
            {t('userNotFound.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-sm text-muted-foreground space-y-2">
            <div className="flex items-start gap-2">
              <span className="w-1 h-1 bg-muted-foreground rounded-full mt-2 flex-shrink-0"></span>
              <span>{t('userNotFound.reasons.incomplete')}</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="w-1 h-1 bg-muted-foreground rounded-full mt-2 flex-shrink-0"></span>
              <span>{t('userNotFound.reasons.deleted')}</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="w-1 h-1 bg-muted-foreground rounded-full mt-2 flex-shrink-0"></span>
              <span>{t('userNotFound.reasons.sync')}</span>
            </div>
          </div>

          {user?.emailAddresses[0]?.emailAddress && (
            <div className="p-3 bg-muted rounded-lg">
              <p className="text-xs text-muted-foreground">
                <strong className="text-foreground">{t('userNotFound.email')}:</strong> {user.emailAddresses[0].emailAddress}
              </p>
            </div>
          )}

          <div className="space-y-2">
            <Button onClick={handleRetry} className="w-full" variant="default">
              <IconRefresh className="w-4 h-4 mr-2" />
              {t('userNotFound.buttons.tryAgain')}
            </Button>

            <Button onClick={handleContactSupport} className="w-full" variant="outline">
              <IconMail className="w-4 h-4 mr-2" />
              {t('userNotFound.buttons.contactSupport')}
            </Button>

            <Button onClick={handleReRegister} className="w-full" variant="outline">
              <IconUserPlus className="w-4 h-4 mr-2" />
              {t('userNotFound.buttons.reRegister')}
            </Button>

            <Button onClick={handleSignOut} className="w-full" variant="ghost">
              <IconHome className="w-4 h-4 mr-2" />
              {t('userNotFound.buttons.signOutHome')}
            </Button>
          </div>

          <div className="text-center">
            <p className="text-xs text-muted-foreground">
              {t('userNotFound.footer')}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
