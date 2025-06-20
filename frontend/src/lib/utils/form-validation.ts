import { z } from "zod"

// Common validation patterns
export const emailSchema = z
  .string()
  .email("Invalid email address")
  .min(1, "Email is required")

export const phoneSchema = z
  .string()
  .regex(/^\+?[1-9]\d{1,14}$/, "Invalid phone number format")
  .optional()

export const urlSchema = z
  .string()
  .url("Invalid URL")
  .startsWith("https://", "URL must use HTTPS")

export const passwordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters")
  .regex(/[A-Z]/, "Password must contain at least one uppercase letter")
  .regex(/[a-z]/, "Password must contain at least one lowercase letter")
  .regex(/[0-9]/, "Password must contain at least one number")
  .regex(/[^A-Za-z0-9]/, "Password must contain at least one special character")

export const strongPasswordSchema = passwordSchema
  .min(12, "Password must be at least 12 characters")

// UUID validation
export const uuidSchema = z.string().uuid("Invalid ID format")

// Date range validation
export const dateRangeSchema = z.object({
  startDate: z.date(),
  endDate: z.date(),
}).refine(
  (data) => data.endDate >= data.startDate,
  {
    message: "End date must be after start date",
    path: ["endDate"],
  }
)

// File validation
export const fileSchema = z.object({
  name: z.string(),
  size: z.number(),
  type: z.string(),
})

export const imageFileSchema = fileSchema.extend({
  type: z.string().regex(/^image\/(jpeg|jpg|png|gif|webp)$/, "Must be an image file"),
  size: z.number().max(5 * 1024 * 1024, "Image must be less than 5MB"),
})

export const documentFileSchema = fileSchema.extend({
  type: z.string().regex(
    /^(application\/(pdf|msword|vnd\.openxmlformats-officedocument\.wordprocessingml\.document)|text\/plain)$/,
    "Must be a document file (PDF, Word, or Text)"
  ),
  size: z.number().max(50 * 1024 * 1024, "Document must be less than 50MB"),
})

// Common field transformers
export const trimString = z.string().transform((val) => val.trim())
export const toLowerCase = z.string().transform((val) => val.toLowerCase())
export const toUpperCase = z.string().transform((val) => val.toUpperCase())

// Sanitization helpers
export const sanitizeFileName = (fileName: string): string => {
  return fileName
    .replace(/[^a-zA-Z0-9.-]/g, '_')
    .replace(/_{2,}/g, '_')
    .replace(/^_+|_+$/g, '')
}

export const sanitizeHtml = (html: string): string => {
  // Basic HTML sanitization - in production, use a library like DOMPurify
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>/gi, '')
    .replace(/on\w+\s*=\s*"[^"]*"/gi, '')
    .replace(/on\w+\s*=\s*'[^']*'/gi, '')
}

// Error message helpers
export const getFieldError = (
  errors: any,
  fieldName: string
): string | undefined => {
  const fieldParts = fieldName.split('.')
  let error = errors

  for (const part of fieldParts) {
    if (error?.[part]) {
      error = error[part]
    } else {
      return undefined
    }
  }

  return error?.message
}

// Form state helpers
export const hasErrors = (errors: any): boolean => {
  return Object.keys(errors).length > 0
}

export const getErrorCount = (errors: any): number => {
  const countErrors = (obj: any): number => {
    let count = 0
    for (const key in obj) {
      if (obj[key]?.message) {
        count++
      } else if (typeof obj[key] === 'object') {
        count += countErrors(obj[key])
      }
    }
    return count
  }
  return countErrors(errors)
}

// Async validation helpers
export const debounceValidation = (
  validator: (value: any) => Promise<boolean>,
  delay: number = 500
) => {
  let timeoutId: NodeJS.Timeout

  return (value: any): Promise<boolean> => {
    clearTimeout(timeoutId)
    
    return new Promise((resolve) => {
      timeoutId = setTimeout(async () => {
        const result = await validator(value)
        resolve(result)
      }, delay)
    })
  }
}

// Custom validation messages
export const validationMessages = {
  required: (field: string) => `${field} is required`,
  minLength: (field: string, min: number) => `${field} must be at least ${min} characters`,
  maxLength: (field: string, max: number) => `${field} must be at most ${max} characters`,
  email: "Please enter a valid email address",
  url: "Please enter a valid URL",
  number: "Please enter a valid number",
  integer: "Please enter a whole number",
  positive: "Please enter a positive number",
  date: "Please enter a valid date",
  future: "Please select a future date",
  past: "Please select a past date",
}