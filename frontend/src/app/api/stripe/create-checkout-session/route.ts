import { auth, currentUser } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'
import Stripe from 'stripe'

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: '2023-10-16',
})

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const { plan, interval, successUrl, cancelUrl, userEmail } = body

    // Try to get user from Clerk session
    const { userId } = auth()
    let email = userEmail // Use provided email as fallback
    
    if (userId) {
      // If we have a userId, try to get user details
      try {
        const user = await currentUser()
        if (user?.emailAddresses?.[0]) {
          email = user.emailAddresses[0].emailAddress
        }
      } catch (error) {
        console.log('Could not fetch current user, using provided email')
      }
    }
    
    // If still no email, try from request body or return error
    if (!email) {
      return NextResponse.json(
        { error: 'Email is required to create checkout session' },
        { status: 400 }
      )
    }

    // Get price ID based on plan and interval
    const priceId = getPriceId(plan, interval)
    
    if (!priceId) {
      return NextResponse.json(
        { error: 'Invalid plan or interval' },
        { status: 400 }
      )
    }

    // Create Stripe checkout session
    const session = await stripe.checkout.sessions.create({
      payment_method_types: ['card'],
      line_items: [
        {
          price: priceId,
          quantity: 1,
        },
      ],
      mode: 'subscription',
      success_url: successUrl || `${process.env.NEXT_PUBLIC_APP_URL}/onboarding?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: cancelUrl || `${process.env.NEXT_PUBLIC_APP_URL}/pricing`,
      customer_email: email,
      metadata: {
        userId: userId,
        plan: plan,
        interval: interval,
      },
      subscription_data: {
        metadata: {
          userId: userId,
          plan: plan,
        },
      },
    })

    return NextResponse.json({ url: session.url })
  } catch (error) {
    console.error('Error creating checkout session:', error)
    return NextResponse.json(
      { error: 'Failed to create checkout session' },
      { status: 500 }
    )
  }
}

function getPriceId(plan: string, interval: string): string | null {
  const prices: Record<string, Record<string, string>> = {
    pro: {
      monthly: process.env.NEXT_PUBLIC_STRIPE_PRO_PRICE_ID!,
      yearly: process.env.NEXT_PUBLIC_STRIPE_PRO_YEARLY_PRICE_ID!,
    },
    enterprise: {
      monthly: process.env.NEXT_PUBLIC_STRIPE_ENTERPRISE_PRICE_ID!,
      yearly: process.env.NEXT_PUBLIC_STRIPE_ENTERPRISE_YEARLY_PRICE_ID!,
    },
  }

  return prices[plan]?.[interval] || null
}