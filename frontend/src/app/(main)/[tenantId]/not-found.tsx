'use client'

import Link from 'next/link'
import { useRouter, useParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { 
  IconHome, 
  IconArrowLeft, 
  IconSearch,
  IconFiles,
  IconMoodConfuzed,
  IconCompass
} from '@tabler/icons-react'
import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'

export default function TenantNotFound() {
  const router = useRouter()
  const params = useParams()
  const tenantId = params?.tenantId as string
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const suggestions = [
    { icon: IconHome, text: 'Dashboard', href: `/${tenantId}/dashboard` },
    { icon: IconFiles, text: 'Documents', href: `/${tenantId}/documents` },
    { icon: IconSearch, text: 'Search', href: `/${tenantId}/search` },
  ]

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center p-6">
      <div className="relative w-full max-w-2xl text-center">
        {/* Animated background elements */}
        <div className="absolute inset-0 overflow-hidden">
          <div className={cn(
            "absolute -left-16 top-0 h-64 w-64 rounded-full bg-gradient-to-br from-purple-400/10 to-pink-400/10 blur-3xl",
            mounted && "animate-pulse"
          )} />
          <div className={cn(
            "absolute -right-16 bottom-0 h-64 w-64 rounded-full bg-gradient-to-br from-blue-400/10 to-cyan-400/10 blur-3xl",
            mounted && "animate-pulse animation-delay-2000"
          )} />
        </div>

        {/* Content */}
        <div className="relative z-10 space-y-6">
          {/* Icon and 404 */}
          <div className={cn(
            "space-y-4",
            mounted && "animate-in fade-in slide-in-from-bottom-4 duration-700"
          )}>
            <div className="relative inline-block">
              <IconCompass className="h-24 w-24 text-muted-foreground/30" />
              <IconMoodConfuzed className="absolute bottom-0 right-0 h-12 w-12 text-muted-foreground/60" />
            </div>
            <h1 className="text-7xl font-bold text-muted-foreground/40">404</h1>
          </div>

          {/* Error message */}
          <div className={cn(
            "space-y-3",
            mounted && "animate-in fade-in slide-in-from-bottom-4 duration-700 delay-200"
          )}>
            <h2 className="text-2xl font-semibold">
              Page not found
            </h2>
            <p className="mx-auto max-w-md text-muted-foreground">
              We couldn't find the page you're looking for. It may have been moved or doesn't exist.
            </p>
          </div>

          {/* Action buttons */}
          <div className={cn(
            "flex flex-col items-center justify-center gap-3 sm:flex-row",
            mounted && "animate-in fade-in slide-in-from-bottom-4 duration-700 delay-400"
          )}>
            <Button
              variant="default"
              onClick={() => router.back()}
              className="group w-full sm:w-auto"
            >
              <IconArrowLeft className="mr-2 h-4 w-4 transition-transform group-hover:-translate-x-1" />
              Go Back
            </Button>
            <Button
              variant="outline"
              asChild
              className="w-full sm:w-auto"
            >
              <Link href={`/${tenantId}/dashboard`}>
                <IconHome className="mr-2 h-4 w-4" />
                Dashboard
              </Link>
            </Button>
          </div>

          {/* Quick links */}
          <div className={cn(
            "pt-6",
            mounted && "animate-in fade-in slide-in-from-bottom-4 duration-700 delay-600"
          )}>
            <p className="mb-3 text-sm text-muted-foreground">
              Quick links:
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {suggestions.map((item, index) => (
                <Link
                  key={index}
                  href={item.href}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-md bg-muted/50 px-3 py-1.5 text-sm",
                    "transition-all hover:bg-muted hover:shadow-sm",
                    "focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
                  )}
                >
                  <item.icon className="h-3.5 w-3.5 text-muted-foreground" />
                  <span>{item.text}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}