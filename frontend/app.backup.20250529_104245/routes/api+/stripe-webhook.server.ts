// frontend/app/routes/api+/stripe-webhook.server.ts
import type { ActionFunctionArgs } from "@remix-run/node";
import { json } from "@remix-run/node";

/**
 * Webhook handler para eventos de Stripe
 * 
 * IMPORTANTE: Este endpoint solo debe reenviar los webhooks al backend
 * El procesamiento real de los webhooks debe hacerse en el backend
 * para mantener la lógica de negocio centralizada
 */

export const action = async ({ request }: ActionFunctionArgs) => {
  const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || 'http://localhost:8000';
  
  try {
    // Obtener el cuerpo del webhook tal como viene de Stripe
    const body = await request.text();
    
    // Obtener los headers necesarios para la verificación
    const stripeSignature = request.headers.get('stripe-signature');
    
    if (!stripeSignature) {
      console.error('Webhook sin firma de Stripe');
      return new Response('Missing Stripe signature', { status: 400 });
    }

    // Reenviar el webhook al backend manteniendo todos los headers relevantes
    const backendResponse = await fetch(`${BACKEND_BASE_URL}/api/v1/webhooks/stripe`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'stripe-signature': stripeSignature,
        // Agregar cualquier otro header que el backend pueda necesitar
        'User-Agent': request.headers.get('User-Agent') || 'RemixApp/1.0',
      },
      body: body,
    });

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();
      console.error(`Backend webhook processing failed: ${backendResponse.status} - ${errorText}`);
      
      // Devolver el mismo código de estado que el backend para que Stripe lo maneje apropiadamente
      return new Response(errorText, { status: backendResponse.status });
    }

    const result = await backendResponse.json();
    console.log('Webhook procesado exitosamente en el backend:', result);

    return json({ received: true, processed: result });

  } catch (error) {
    console.error('Error processing Stripe webhook:', error);
    
    // Devolver 500 para que Stripe reintente el webhook
    return new Response(
      JSON.stringify({ error: 'Internal server error processing webhook' }), 
      { 
        status: 500,
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }
};

// Solo permitir POST requests
export const loader = async () => {
  return new Response('Method not allowed', { status: 405 });
};