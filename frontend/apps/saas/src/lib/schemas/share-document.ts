import { z } from "zod"

// Share type enum
export const shareTypeEnum = z.enum(["link", "email"])

// Permissions schema
export const permissionsSchema = z.object({
  canView: z.boolean().default(true),
  canDownload: z.boolean().default(false),
  canComment: z.boolean().default(false),
  canSign: z.boolean().default(false),
})

// Base share schema
const baseShareSchema = z.object({
  shareType: shareTypeEnum,
  message: z.string().max(500, "Message too long").optional(),
  expiresIn: z.number()
    .min(1, "Minimum 1 hour")
    .max(8760, "Maximum 1 year (8760 hours)")
    .nullable()
    .optional(),
  maxAccessCount: z.number()
    .min(1, "Minimum 1 access")
    .max(1000, "Maximum 1000 accesses")
    .nullable()
    .optional(),
  permissions: permissionsSchema,
})

// Email share specific fields
const emailShareSchema = baseShareSchema.extend({
  shareType: z.literal("email"),
  recipientEmail: z.string()
    .email("Invalid email address")
    .min(1, "Email is required"),
  recipientName: z.string()
    .min(1, "Name is required")
    .max(100, "Name too long"),
})

// Link share specific fields
const linkShareSchema = baseShareSchema.extend({
  shareType: z.literal("link"),
  password: z.string()
    .min(8, "Password must be at least 8 characters")
    .regex(/[A-Z]/, "Password must contain at least one uppercase letter")
    .regex(/[a-z]/, "Password must contain at least one lowercase letter")
    .regex(/[0-9]/, "Password must contain at least one number")
    .optional()
    .nullable(),
  requireEmail: z.boolean().default(false),
})

// Combined schema with discriminated union
export const shareDocumentSchema = z.discriminatedUnion("shareType", [
  emailShareSchema,
  linkShareSchema,
])

// Type inference
export type ShareDocumentFormData = z.infer<typeof shareDocumentSchema>
export type SharePermissions = z.infer<typeof permissionsSchema>
export type EmailShareData = z.infer<typeof emailShareSchema>
export type LinkShareData = z.infer<typeof linkShareSchema>

// Helper to get default values by share type
export function getDefaultShareValues(shareType: "link" | "email"): ShareDocumentFormData {
  const baseDefaults = {
    message: "",
    expiresIn: 24, // 24 hours default
    maxAccessCount: null,
    permissions: {
      canView: true,
      canDownload: false,
      canComment: false,
      canSign: false,
    },
  }

  if (shareType === "email") {
    return {
      ...baseDefaults,
      shareType: "email",
      recipientEmail: "",
      recipientName: "",
    }
  }

  return {
    ...baseDefaults,
    shareType: "link",
    password: null,
    requireEmail: false,
  }
}