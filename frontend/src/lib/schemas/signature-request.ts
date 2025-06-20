import { z } from "zod"

// Signer schema
export const signerSchema = z.object({
  email: z.string().email("Invalid email address"),
  name: z.string().min(1, "Name is required"),
  role: z.enum(["signer", "approver", "viewer"]).default("signer"),
  order: z.number().min(1).default(1),
  phone: z.string().optional(),
  authentication_method: z.enum(["email", "sms", "none"]).optional(),
})

// Signature request form schema
export const signatureRequestSchema = z.object({
  title: z.string().min(1, "Title is required").max(200, "Title too long"),
  message: z.string().max(1000, "Message too long").optional(),
  signers: z.array(signerSchema)
    .min(1, "At least one signer is required")
    .max(10, "Maximum 10 signers allowed"),
  provider_id: z.string().uuid("Please select a valid provider"),
  expires_in_days: z.number()
    .min(1, "Minimum 1 day")
    .max(365, "Maximum 365 days")
    .default(30),
  document_id: z.string().uuid(),
})

// Type inference
export type SignatureRequestFormData = z.infer<typeof signatureRequestSchema>
export type SignerFormData = z.infer<typeof signerSchema>

// Partial schemas for drafts
export const signatureRequestDraftSchema = signatureRequestSchema.partial({
  message: true,
  provider_id: true,
})

export type SignatureRequestDraftData = z.infer<typeof signatureRequestDraftSchema>