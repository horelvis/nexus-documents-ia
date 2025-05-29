// frontend/app/utils/env.server.ts
import { z } from 'zod'

const schema = z.object({
  NODE_ENV: z.enum(['production', 'development', 'test'] as const),
  SESSION_SECRET: z.string().optional(),
  ENCRYPTION_SECRET: z.string().optional(),
  DEV_HOST_URL: z.string().optional(),
  PROD_HOST_URL: z.string().optional(),
  RESEND_API_KEY: z.string(),
  STRIPE_SECRET_KEY: z.string(),
  STRIPE_WEBHOOK_ENDPOINT: z.string().optional(),
  HONEYPOT_ENCRYPTION_SEED: z.string().optional(),
  
  // Clerk Environment Variables
  CLERK_PUBLISHABLE_KEY: z.string().min(1, 'CLERK_PUBLISHABLE_KEY is required'),
  CLERK_WEBHOOK_SECRET: z.string().min(1, 'CLERK_WEBHOOK_SECRET is required'),
  
  // Backend API Configuration
  BACKEND_BASE_URL: z.string().default('http://localhost:8000'),
  BACKEND_API_TIMEOUT: z.string().transform(Number).default('30000'),
})

declare global {
  namespace NodeJS {
    interface ProcessEnv extends z.infer<typeof schema> {}
  }
}

export function initEnvs() {
  const parsed = schema.safeParse(process.env)

  if (parsed.success === false) {
    console.error('Invalid environment variables:', parsed.error.flatten().fieldErrors)
    throw new Error('Invalid environment variables.')
  }
}

/**
 * Exports shared environment variables.
 * Do *NOT* add any environment variables that do not wish to be included in the client.
 */
export function getSharedEnvs() {
  return {
    DEV_HOST_URL: process.env.DEV_HOST_URL,
    PROD_HOST_URL: process.env.PROD_HOST_URL,
    BACKEND_BASE_URL: process.env.BACKEND_BASE_URL,
  }
}

/**
 * Environment configuration object
 */
export const ENV = {
  NODE_ENV: process.env.NODE_ENV,
  BACKEND_BASE_URL: process.env.BACKEND_BASE_URL || 'http://localhost:8000',
  BACKEND_API_TIMEOUT: parseInt(process.env.BACKEND_API_TIMEOUT || '30000'),
  CLERK_PUBLISHABLE_KEY: process.env.CLERK_PUBLISHABLE_KEY,
  CLERK_SECRET_KEY: process.env.CLERK_SECRET_KEY,
  CLERK_WEBHOOK_SECRET: process.env.CLERK_WEBHOOK_SECRET,
} as const