import { redirect } from 'next/navigation'

export default async function TenantOnboardingPage({
  params,
}: {
  params: Promise<{ tenantId: string }>
}) {
  const { tenantId } = await params
  
  // Redirect to the main onboarding page
  // The onboarding component will handle tenant context
  redirect('/onboarding')
}