import { Webhook } from 'svix';
import { headers } from 'next/headers';
import { WebhookEvent } from '@clerk/nextjs/server';
import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  // You can find this in the Clerk Dashboard -> Webhooks -> choose the webhook
  const WEBHOOK_SECRET = process.env.CLERK_WEBHOOK_SECRET;

  if (!WEBHOOK_SECRET) {
    throw new Error('Please add CLERK_WEBHOOK_SECRET from Clerk Dashboard to .env or .env.local');
  }

  // Get the headers
  const headerPayload = headers();
  const svix_id = headerPayload.get("svix-id");
  const svix_timestamp = headerPayload.get("svix-timestamp");
  const svix_signature = headerPayload.get("svix-signature");

  // If there are no headers, error out
  if (!svix_id || !svix_timestamp || !svix_signature) {
    return new Response('Error occured -- no svix headers', {
      status: 400
    });
  }

  // Get the body
  const payload = await req.json();
  const body = JSON.stringify(payload);

  // Create a new Svix instance with your secret.
  const wh = new Webhook(WEBHOOK_SECRET);

  let evt: WebhookEvent;

  // Verify the payload with the headers
  try {
    evt = wh.verify(body, {
      "svix-id": svix_id,
      "svix-timestamp": svix_timestamp,
      "svix-signature": svix_signature,
    }) as WebhookEvent;
  } catch (err) {
    console.error('Error verifying webhook:', err);
    return new Response('Error occured', {
      status: 400
    });
  }

  // Handle the webhook event
  const { id } = evt.data;
  const eventType = evt.type;

  console.log(`Webhook with an ID of ${id} and type of ${eventType}`);
  console.log('Webhook body:', body);

  try {
    // Sync user with backend
    if (eventType === 'user.created' || eventType === 'user.updated') {
      const { id: clerkUserId, email_addresses, first_name, last_name } = evt.data;
      
      const primaryEmail = email_addresses.find(email => email.id === evt.data.primary_email_address_id);
      
      if (primaryEmail && clerkUserId) {
        const userData = {
          clerk_user_id: clerkUserId,
          email: primaryEmail.email_address,
          full_name: `${first_name || ''} ${last_name || ''}`.trim() || 'User',
        };

        // Call your backend API to sync the user
        const backendResponse = await fetch(`${process.env.INTERNAL_API_URL}/api/v1/auth/sync-user`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(userData),
        });

        if (!backendResponse.ok) {
          console.error('Failed to sync user with backend:', await backendResponse.text());
        } else {
          console.log('User synced successfully with backend');
        }
      }
    }

    // Handle user deletion
    if (eventType === 'user.deleted') {
      const { id: clerkUserId } = evt.data;
      
      if (clerkUserId) {
        // Call your backend API to handle user deletion
        const backendResponse = await fetch(`${process.env.INTERNAL_API_URL}/api/v1/auth/users/${clerkUserId}`, {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json',
          },
        });

        if (!backendResponse.ok) {
          console.error('Failed to delete user from backend:', await backendResponse.text());
        } else {
          console.log('User deleted successfully from backend');
        }
      }
    }
  } catch (error) {
    console.error('Error processing webhook:', error);
    // Don't return an error response as this might cause Clerk to retry
    // Just log the error and return success
  }

  return new Response('', { status: 200 });
}