"use client"

import { useEffect, useMemo, Suspense } from "react"
import { useSearchParams } from "next/navigation"
import Link from "next/link"
import { Loader2 } from "lucide-react"

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  ""

function GoogleDriveCallbackContent() {
  const searchParams = useSearchParams()

  const queryString = useMemo(() => {
    if (!searchParams) return ""
    const params = new URLSearchParams()
    searchParams.forEach((value, key) => {
      params.set(key, value)
    })
    return params.toString()
  }, [searchParams])

  useEffect(() => {
    if (!queryString) return
    const target = `${API_BASE_URL}/api/v1/google-drive/oauth/callback?${queryString}`
    window.location.replace(target)
  }, [queryString])

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4">
      <div className="max-w-md text-center space-y-4">
        <h1 className="text-2xl font-semibold">Connecting Google Drive…</h1>
        <p className="text-muted-foreground">
          We&apos;re finalizing your Google authorization. You will be redirected automatically.
        </p>
        <p className="text-sm text-muted-foreground">
          If nothing happens,{" "}
          <Link
            href={`${API_BASE_URL}/api/v1/google-drive/oauth/callback?${queryString}`}
            className="text-primary underline"
          >
            click here to continue
          </Link>
          .
        </p>
      </div>
    </div>
  )
}

export default function GoogleDriveCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
         <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    }>
      <GoogleDriveCallbackContent />
    </Suspense>
  )
}
