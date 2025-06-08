import { Suspense } from 'react'
import { SignUpWithCheckout } from '@/components/auth/signup-with-checkout'

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <SignUpWithCheckout />
    </Suspense>
  )
}