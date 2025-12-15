"use client"

import React from 'react'
import { useUser } from '@clerk/nextjs'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { UserDeletionDialog } from "@/components/lgpd/user-deletion-dialog"
import { Shield, User, Mail, Calendar, AlertTriangle, Crown } from 'lucide-react'
import { useTranslation } from '@/lib/i18n/hooks'

export default function UserSettingsPage() {
  const { user, isLoaded } = useUser()
  const { t, language } = useTranslation()

  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="text-center py-8">
        <p className="text-muted-foreground">{t('userSettings.userNotFound')}</p>
      </div>
    )
  }
  
  const locale = language === 'es' ? 'es-ES' : 'en-US';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t('userSettings.title')}</h1>
        <p className="text-muted-foreground">
          {t('userSettings.subtitle')}
        </p>
      </div>

      {/* User Profile Information */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            {t('userSettings.personalInfo.title')}
          </CardTitle>
          <CardDescription>
            {t('userSettings.personalInfo.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">{t('userSettings.personalInfo.fullName')}</label>
              <div className="flex items-center gap-2">
                <span className="text-sm">{user.fullName || t('userSettings.personalInfo.notProvided')}</span>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">{t('userSettings.personalInfo.primaryEmail')}</label>
              <div className="flex items-center gap-2">
                <Mail className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">{user.primaryEmailAddress?.emailAddress}</span>
                {user.primaryEmailAddress?.verification?.status === 'verified' && (
                  <Badge variant="secondary" className="text-xs">
                    <Shield className="h-3 w-3 mr-1" />
                    {t('userSettings.personalInfo.verified')}
                  </Badge>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">{t('userSettings.personalInfo.accountCreated')}</label>
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">
                  {user.createdAt ? new Date(user.createdAt).toLocaleDateString(locale) : t('userSettings.personalInfo.notProvided')}
                </span>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">{t('userSettings.personalInfo.lastSignIn')}</label>
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">
                  {user.lastSignInAt ? new Date(user.lastSignInAt).toLocaleString(locale) : t('userSettings.personalInfo.never')}
                </span>
              </div>
            </div>
          </div>

          {/* Additional User Info */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">{t('userSettings.personalInfo.additionalEmails')}</label>
            <div className="space-y-1">
              {user.emailAddresses?.slice(1).length > 0 ? user.emailAddresses?.slice(1).map((email, index) => (
                <div key={index} className="flex items-center gap-2 text-sm">
                  <Mail className="h-3 w-3 text-muted-foreground" />
                  <span>{email.emailAddress}</span>
                  {email.verification?.status === 'verified' ? (
                    <Badge variant="outline" className="text-xs">{t('userSettings.personalInfo.verified')}</Badge>
                  ) : (
                    <Badge variant="destructive" className="text-xs">{t('userSettings.personalInfo.unverified')}</Badge>
                  )}
                </div>
              )) : (
                <span className="text-sm text-muted-foreground">{t('userSettings.personalInfo.noAdditionalEmails')}</span>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Account Security */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            {t('userSettings.security.title')}
          </CardTitle>
          <CardDescription>
            {t('userSettings.security.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">{t('userSettings.security.twoFactor')}</label>
              <div className="flex items-center gap-2">
                {user.twoFactorEnabled ? (
                  <Badge variant="secondary" className="text-xs">
                    <Shield className="h-3 w-3 mr-1" />
                    {t('userSettings.security.twoFactorEnabled')}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-xs">
                    <AlertTriangle className="h-3 w-3 mr-1" />
                    {t('userSettings.security.twoFactorDisabled')}
                  </Badge>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">{t('userSettings.security.accountStatus')}</label>
              <div className="flex items-center gap-2">
                {(user.publicMetadata as { banned?: boolean })?.banned ? (
                  <Badge variant="destructive" className="text-xs">{t('userSettings.security.banned')}</Badge>
                ) : (
                  <Badge variant="secondary" className="text-xs">
                    <Shield className="h-3 w-3 mr-1" />
                    {t('userSettings.security.active')}
                  </Badge>
                )}
              </div>
            </div>
          </div>

          <Alert>
            <Shield className="h-4 w-4" />
            <AlertTitle>{t('userSettings.security.manageSecurity.title')}</AlertTitle>
            <AlertDescription dangerouslySetInnerHTML={{ __html: t('userSettings.security.manageSecurity.description') }} />
          </Alert>
        </CardContent>
      </Card>

      <Separator />

      {/* Data Protection Section */}
      <Card className="border-red-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-red-600">
            <AlertTriangle className="h-5 w-5" />
            {t('userSettings.dataProtection.title')}
          </CardTitle>
          <CardDescription>
            {t('userSettings.dataProtection.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-4">
            <div>
              <h4 className="font-medium mb-2">{t('userSettings.dataProtection.yourRights')}</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-muted-foreground">
                <div className="space-y-2">
                  <div className="flex items-start gap-2">
                    <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 flex-shrink-0"></div>
                    <div dangerouslySetInnerHTML={{ __html: t('userSettings.dataProtection.rights.access') }} />
                  </div>
                  <div className="flex items-start gap-2">
                    <div className="w-2 h-2 bg-green-500 rounded-full mt-2 flex-shrink-0"></div>
                    <div dangerouslySetInnerHTML={{ __html: t('userSettings.dataProtection.rights.correction') }} />
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex items-start gap-2">
                    <div className="w-2 h-2 bg-yellow-500 rounded-full mt-2 flex-shrink-0"></div>
                    <div dangerouslySetInnerHTML={{ __html: t('userSettings.dataProtection.rights.portability') }} />
                  </div>
                  <div className="flex items-start gap-2">
                    <div className="w-2 h-2 bg-red-500 rounded-full mt-2 flex-shrink-0"></div>
                    <div dangerouslySetInnerHTML={{ __html: t('userSettings.dataProtection.rights.erasure') }} />
                  </div>
                </div>
              </div>
            </div>

            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>{t('userSettings.dataProtection.dangerZone.title')}</AlertTitle>
              <AlertDescription className="space-y-2">
                <p dangerouslySetInnerHTML={{ __html: t('userSettings.dataProtection.dangerZone.description1') }} />
                <p className="font-medium" dangerouslySetInnerHTML={{ __html: t('userSettings.dataProtection.dangerZone.description2') }} />
              </AlertDescription>
            </Alert>

            <div className="flex justify-between items-center pt-4">
              <div>
                <p className="text-sm font-medium">{t('userSettings.dataProtection.fullDeletion.title')}</p>
                <p className="text-sm text-muted-foreground">
                  {t('userSettings.dataProtection.fullDeletion.description')}
                </p>
              </div>
              <UserDeletionDialog />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Legal Information */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Crown className="h-5 w-5" />
            {t('userSettings.legal.title')}
          </CardTitle>
          <CardDescription>
            {t('userSettings.legal.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-sm text-muted-foreground space-y-2">
            <p dangerouslySetInnerHTML={{ __html: t('userSettings.legal.applicableLaw') }} />
            <p dangerouslySetInnerHTML={{ __html: t('userSettings.legal.legalBasis') }} />
            <p dangerouslySetInnerHTML={{ __html: t('userSettings.legal.purpose') }} />
            <p dangerouslySetInnerHTML={{ __html: t('userSettings.legal.retention') }} />
            <p dangerouslySetInnerHTML={{ __html: t('userSettings.legal.controller') }} />
          </div>

          <Alert>
            <Shield className="h-4 w-4" />
            <AlertDescription dangerouslySetInnerHTML={{ __html: t('userSettings.legal.contact') }} />
          </Alert>
        </CardContent>
      </Card>
    </div>
  )
}