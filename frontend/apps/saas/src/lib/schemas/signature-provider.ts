import { z } from "zod"

// Base provider schema
const baseProviderSchema = z.object({
  displayName: z.string()
    .min(1, "Display name is required")
    .max(100, "Display name too long"),
  isActive: z.boolean().default(true),
  isDefault: z.boolean().default(false),
})

// DocuSign credentials schema
const docusignCredentialsSchema = z.object({
  integration_key: z.string().min(1, "Integration key is required"),
  secret_key: z.string().min(1, "Secret key is required"),
  account_id: z.string().min(1, "Account ID is required"),
  base_url: z.string().url("Invalid base URL").optional(),
  environment: z.enum(["sandbox", "production"]).default("sandbox"),
})

// YouSign credentials schema
const yousignCredentialsSchema = z.object({
  api_key: z.string().min(1, "API key is required"),
  environment: z.enum(["sandbox", "production"]).default("sandbox"),
  webhook_secret: z.string().optional(),
})

// Signaturit credentials schema
const signaturitCredentialsSchema = z.object({
  access_token: z.string().min(1, "Access token is required"),
  environment: z.enum(["sandbox", "production"]).default("sandbox"),
  webhook_secret: z.string().optional(),
})

// Provider type enum
export const providerTypeEnum = z.enum(["docusign", "yousign", "signaturit"])
export type ProviderType = z.infer<typeof providerTypeEnum>

// Combined provider schema with discriminated union
export const signatureProviderSchema = z.discriminatedUnion("providerName", [
  z.object({
    providerName: z.literal("docusign"),
    ...baseProviderSchema.shape,
    credentials: docusignCredentialsSchema,
  }),
  z.object({
    providerName: z.literal("yousign"),
    ...baseProviderSchema.shape,
    credentials: yousignCredentialsSchema,
  }),
  z.object({
    providerName: z.literal("signaturit"),
    ...baseProviderSchema.shape,
    credentials: signaturitCredentialsSchema,
  }),
])

// Type inference
export type SignatureProviderFormData = z.infer<typeof signatureProviderSchema>
export type DocuSignCredentials = z.infer<typeof docusignCredentialsSchema>
export type YouSignCredentials = z.infer<typeof yousignCredentialsSchema>
export type SignaturitCredentials = z.infer<typeof signaturitCredentialsSchema>

// Helper function to get credentials schema by provider type
export function getCredentialsSchema(providerType: ProviderType) {
  switch (providerType) {
    case "docusign":
      return docusignCredentialsSchema
    case "yousign":
      return yousignCredentialsSchema
    case "signaturit":
      return signaturitCredentialsSchema
  }
}

// Validation messages for better UX
export const providerValidationMessages = {
  docusign: {
    integration_key: "You can find this in your DocuSign admin panel",
    secret_key: "Keep this secure - it's your DocuSign secret",
    account_id: "Your DocuSign account ID",
    base_url: "Leave empty for default URL",
  },
  yousign: {
    api_key: "Get this from your YouSign dashboard",
    webhook_secret: "Optional - for webhook signature verification",
  },
  signaturit: {
    access_token: "Your Signaturit API access token",
    webhook_secret: "Optional - for webhook security",
  },
}