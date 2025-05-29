import type { ActionFunctionArgs } from "@remix-run/node";
import { Webhook } from "svix";
import { prisma } from "#app/utils/db.server"; // Adjust if your prisma client path is different
import { ENV } from "#app/utils/env.server";

// Define the Event type based on Clerk's webhook payload structure
interface EventData {
  id: string; // This is the Clerk User ID
  email_addresses?: { email_address: string, id: string, verification: any }[]; // Clerk's email structure
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  image_url?: string | null;
  // Add other attributes you expect from Clerk user object
  // For example, 'public_metadata', 'private_metadata' if you use them.
}

interface Event {
  data: EventData;
  object: "event";
  type: "user.created" | "user.updated" | "user.deleted" | string; // Add other event types
}


export const action = async ({ request }: ActionFunctionArgs) => {
  const { CLERK_WEBHOOK_SECRET } = ENV;
  if (!CLERK_WEBHOOK_SECRET) {
    console.error("Clerk webhook secret is not configured.");
    // It's crucial to return a 500 error if the secret is missing,
    // otherwise, the webhook provider might retry indefinitely or disable the webhook.
    return new Response("Server configuration error: Webhook secret missing", { status: 500 });
  }

  const headers = request.headers;
  const svix_id = headers.get("svix-id");
  const svix_timestamp = headers.get("svix-timestamp");
  const svix_signature = headers.get("svix-signature");

  if (!svix_id || !svix_timestamp || !svix_signature) {
    console.warn("Webhook request missing Svix headers.");
    return new Response("Error occurred -- no Svix headers", { status: 400 });
  }

  let payloadString: string;
  try {
    payloadString = await request.text(); // Read the raw body as text
  } catch (err) {
    console.error("Error reading webhook request body:", err);
    return new Response("Error reading request body", { status: 400 });
  }
  
  const wh = new Webhook(CLERK_WEBHOOK_SECRET);
  let evt: Event;
  try {
    evt = wh.verify(payloadString, {
      "svix-id": svix_id,
      "svix-timestamp": svix_timestamp,
      "svix-signature": svix_signature,
    }) as Event;
  } catch (err: any) { // Catching 'any' type for error flexibility
    console.error("Error verifying webhook:", err.message || err);
    return new Response("Error occurred during webhook verification", { status: 400 });
  }

  const { id: clerkUserId, ...attributes } = evt.data;
  const eventType = evt.type;

  console.log(`Received webhook event: ${eventType} for Clerk User ID: ${clerkUserId}`);

  try {
    if (eventType === "user.created") {
      const primaryEmailObject = attributes.email_addresses?.find(
        // Clerk typically marks primary email, but let's assume the first one if not specified.
        // Or, if there's an ID for primary: email => email.id === attributes.primary_email_address_id
        (email) => email.email_address 
      );
      const email = primaryEmailObject?.email_address;

      if (!email) {
        console.error(`User created event for Clerk ID ${clerkUserId} without a primary email address.`);
        return new Response("Error: Email missing in user.created event", { status: 400 });
      }

      // Check if user already exists by clerkUserId (idempotency) or by email (linking)
      let existingUser = await prisma.user.findUnique({ where: { clerkUserId } });
      if (existingUser) {
        console.log(`User with Clerk ID ${clerkUserId} already exists (ID: ${existingUser.id}). Webhook processed idempotently.`);
        return new Response("User already exists, processed idempotently.", { status: 200 });
      }
      
      existingUser = await prisma.user.findUnique({ where: { email } });
      if (existingUser) {
        // User with this email exists, link it to the new Clerk ID
        await prisma.user.update({
          where: { id: existingUser.id },
          data: { 
            clerkUserId: clerkUserId,
            username: existingUser.username || attributes.username || email, // Keep existing username or update
            // Update other attributes if necessary, e.g., image
            // image: attributes.image_url ? { upsert: { create: { /* ... */ }, update: { /* ... */ } } } : undefined,
          },
        });
        console.log(`Linked existing user with email ${email} (ID: ${existingUser.id}) to Clerk ID ${clerkUserId}`);
      } else {
        // Create new user
        await prisma.user.create({
          data: {
            clerkUserId: clerkUserId,
            email,
            username: attributes.username || email, // Default username to email if not provided
            // UserImage relation needs specific handling based on your schema if attributes.image_url exists
            // For example, if UserImage is a separate model:
            // image: attributes.image_url ? { create: { blob: Buffer.from(attributes.image_url), contentType: 'text/plain' } } : undefined,
          },
        });
        console.log(`Created new user for Clerk ID ${clerkUserId} with email ${email}`);
      }
    } else if (eventType === "user.updated") {
      if (!clerkUserId) return new Response("Error: clerkUserId missing for user.updated event", { status: 400 });
      
      const primaryEmailObject = attributes.email_addresses?.find(email => email.email_address);
      const email = primaryEmailObject?.email_address;

      if (!email) {
        console.error(`User updated event for Clerk ID ${clerkUserId} without a primary email address.`);
        return new Response("Error: Email missing in user.updated event", { status: 400 });
      }

      await prisma.user.updateMany({ // Use updateMany as clerkUserId is not necessarily the primary key 'id'
        where: { clerkUserId: clerkUserId },
        data: {
          email: email,
          username: attributes.username || email,
          // Update other attributes like UserImage if image_url changed
        },
      });
      console.log(`Updated user details for Clerk ID ${clerkUserId}`);
    } else if (eventType === "user.deleted") {
      if (!clerkUserId) return new Response("Error: clerkUserId missing for user.deleted event", { status: 400 });
      
      // Soft delete (mark as inactive) or hard delete
      // For hard delete:
      const deletedUser = await prisma.user.deleteMany({ // Use deleteMany if clerkUserId is not primary key
        where: { clerkUserId: clerkUserId },
      });
      if (deletedUser.count > 0) {
        console.log(`Deleted user(s) associated with Clerk ID ${clerkUserId}`);
      } else {
        console.warn(`No user found to delete for Clerk ID ${clerkUserId}`);
      }
    } else {
      console.log(`Received unhandled event type: ${eventType}`);
    }
  } catch (dbError: any) {
    console.error(`Database error processing webhook event ${eventType} for Clerk User ID ${clerkUserId}:`, dbError.message || dbError);
    return new Response("Internal server error during database operation", { status: 500 });
  }

  return new Response("", { status: 200 });
};
