import { headers } from 'next/headers'
import { WebhookEvent } from '@clerk/nextjs/server'
import { Webhook } from 'svix'

export async function POST(req: Request) {
  // Get the headers
  const headerPayload = headers()
  const svix_id = headerPayload.get("svix-id")
  const svix_timestamp = headerPayload.get("svix-timestamp")
  const svix_signature = headerPayload.get("svix-signature")

  // If there are no headers, error out
  if (!svix_id || !svix_timestamp || !svix_signature) {
    return new Response('Error occured -- no svix headers', {
      status: 400
    })
  }

  // Get the body
  const payload = await req.json()
  const body = JSON.stringify(payload)

  // Create a new Svix instance with your secret.
  const wh = new Webhook(process.env.CLERK_WEBHOOK_SECRET || '')

  let evt: WebhookEvent

  // Verify the payload with the headers
  try {
    evt = wh.verify(body, {
      "svix-id": svix_id,
      "svix-timestamp": svix_timestamp,
      "svix-signature": svix_signature,
    }) as WebhookEvent
  } catch (err) {
    console.error('Error verifying webhook:', err)
    return new Response('Error occured', {
      status: 400
    })
  }

  // Handle the webhook
  const eventType = evt.type

  if (eventType === 'user.created') {
    const { id, email_addresses, unsafe_metadata } = evt.data
    const email = email_addresses[0]?.email_address
    const plan = unsafe_metadata?.plan as string || 'free'
    const interval = unsafe_metadata?.interval as string || 'monthly'

    // Create user in our database
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          clerk_user_id: id,
          email: email,
          plan: plan,
          interval: interval,
        }),
      })

      if (!response.ok) {
        console.error('Failed to create user in database')
      }

      // If user selected a paid plan, trigger Stripe checkout
      if (plan !== 'free' && plan !== 'enterprise') {
        // This will be handled in the frontend after sign-up
        console.log('User needs to complete Stripe checkout for plan:', plan)
      }
    } catch (error) {
      console.error('Error creating user:', error)
    }
  }

  return new Response('', { status: 200 })
}