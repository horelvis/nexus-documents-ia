'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { 
  IconHome, 
  IconArrowLeft, 
  IconSearch,
  IconRocket,
  IconMoodSad,
  IconBulb
} from '@tabler/icons-react'
import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'

export default function NotFound() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const suggestions = [
    { icon: IconHome, text: 'Go to Dashboard', href: '/dashboard' },
    { icon: IconSearch, text: 'Search Documents', href: '/search' },
    { icon: IconBulb, text: 'View Help Center', href: '/help' },
  ]

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-background to-muted/20">
      <div className="relative w-full max-w-2xl px-6 py-12 text-center">
        {/* Animated background elements */}
        <div className="absolute inset-0 overflow-hidden">
          <div className={cn(
            "absolute -left-4 top-1/4 h-72 w-72 rounded-full bg-purple-300/20 blur-3xl dark:bg-purple-600/10",
            mounted && "animate-pulse"
          )} />
          <div className={cn(
            "absolute -right-4 bottom-1/4 h-72 w-72 rounded-full bg-blue-300/20 blur-3xl dark:bg-blue-600/10",
            mounted && "animate-pulse animation-delay-2000"
          )} />
        </div>

        {/* Content */}
        <div className="relative z-10 space-y-8">
          {/* 404 Number */}
          <div className="relative">
            <h1 className={cn(
              "text-[150px] font-bold leading-none text-muted-foreground/20 md:text-[200px]",
              mounted && "animate-in fade-in slide-in-from-bottom-4 duration-700"
            )}>
              404
            </h1>
            <div className={cn(
              "absolute inset-0 flex items-center justify-center",
              mounted && "animate-in fade-in zoom-in-50 duration-700 delay-200"
            )}>
              <IconMoodSad className="h-20 w-20 text-muted-foreground/60 md:h-24 md:w-24" />
            </div>
          </div>

          {/* Error message */}
          <div className={cn(
            "space-y-4",
            mounted && "animate-in fade-in slide-in-from-bottom-4 duration-700 delay-300"
          )}>
            <h2 className="text-2xl font-semibold text-foreground md:text-3xl">
              Oops! Page not found
            </h2>
            <p className="mx-auto max-w-md text-muted-foreground">
              The page you're looking for seems to have wandered off. 
              It might have been moved, deleted, or perhaps it never existed.
            </p>
          </div>

          {/* Action buttons */}
          <div className={cn(
            "flex flex-col items-center justify-center gap-4 sm:flex-row",
            mounted && "animate-in fade-in slide-in-from-bottom-4 duration-700 delay-500"
          )}>
            <Button
              variant="default"
              size="lg"
              onClick={() => router.back()}
              className="group w-full sm:w-auto"
            >
              <IconArrowLeft className="mr-2 h-4 w-4 transition-transform group-hover:-translate-x-1" />
              Go Back
            </Button>
            <Button
              variant="outline"
              size="lg"
              asChild
              className="w-full sm:w-auto"
            >
              <Link href="/" className="group">
                <IconHome className="mr-2 h-4 w-4 transition-transform group-hover:scale-110" />
                Home Page
              </Link>
            </Button>
          </div>

          {/* Suggestions */}
          <div className={cn(
            "pt-8",
            mounted && "animate-in fade-in slide-in-from-bottom-4 duration-700 delay-700"
          )}>
            <p className="mb-4 text-sm text-muted-foreground">
              Here are some helpful links:
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {suggestions.map((item, index) => (
                <Link
                  key={index}
                  href={item.href}
                  className={cn(
                    "group inline-flex items-center gap-2 rounded-full bg-muted px-4 py-2 text-sm",
                    "transition-all hover:bg-muted/80 hover:shadow-md",
                    "focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
                  )}
                >
                  <item.icon className="h-4 w-4 text-muted-foreground transition-colors group-hover:text-primary" />
                  <span className="text-muted-foreground transition-colors group-hover:text-foreground">
                    {item.text}
                  </span>
                </Link>
              ))}
            </div>
          </div>

          {/* Fun element */}
          <div className={cn(
            "pt-8",
            mounted && "animate-in fade-in duration-1000 delay-1000"
          )}>
            <div className="group inline-flex cursor-pointer items-center gap-2 text-xs text-muted-foreground transition-colors hover:text-foreground">
              <IconRocket className="h-4 w-4 transition-transform group-hover:translate-x-1 group-hover:-translate-y-1" />
              <span>Lost in space? Don't worry, we'll help you navigate back!</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}