"use client"

import { Suspense } from 'react'
import { TenantNotFound } from '@/components/errors/tenant-not-found'
import { useSearchParams } from 'next/navigation'

function TenantNotFoundContent() {
  const searchParams = useSearchParams()
  const tenantId = searchParams.get('tenantId')

  return <TenantNotFound tenantId={tenantId || undefined} />
}

export default function TenantNotFoundPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <TenantNotFoundContent />
    </Suspense>
  )
}