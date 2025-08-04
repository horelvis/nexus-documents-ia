import { NextResponse } from 'next/server'
import Stripe from 'stripe'

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: '2023-10-16',
})

export async function GET(
  req: Request,
  { params }: { params: { sessionId: string } }
) {
  try {
    const session = await stripe.checkout.sessions.retrieve(params.sessionId, {
      expand: ['customer', 'subscription'],
    })

    if (!session) {
      return NextResponse.json(
        { error: 'Session not found' },
        { status: 404 }
      )
    }

    // Extract relevant information
    const subscription = session.subscription as Stripe.Subscription
    const customer = session.customer as Stripe.Customer

    return NextResponse.json({
      success: true,
      session_id: session.id,
      customer_id: customer?.id,
      customer_email: customer?.email || session.customer_email,
      subscription_id: subscription?.id,
      plan: session.metadata?.plan || 'free',
      interval: session.metadata?.interval || 'monthly',
      payment_status: session.payment_status,
      amount_total: session.amount_total,
      currency: session.currency,
    })
  } catch (error) {
    console.error('Error verifying session:', error)
    return NextResponse.json(
      { error: 'Failed to verify session' },
      { status: 500 }
    )
  }
}