import { z } from "zod"

// Category schema
export const documentCategorySchema = z.enum([
  "contracts",
  "invoices",
  "reports",
  "presentations",
  "legal",
  "financial",
  "hr",
  "marketing",
  "technical",
  "other"
])

// Tag schema
export const tagSchema = z.object({
  id: z.string().optional(),
  name: z.string()
    .min(1, "Tag cannot be empty")
    .max(30, "Tag too long")
    .regex(/^[a-zA-Z0-9-_]+$/, "Tags can only contain letters, numbers, hyphens, and underscores"),
})

// Edit document schema
export const editDocumentSchema = z.object({
  title: z.string()
    .min(1, "Title is required")
    .max(200, "Title too long")
    .transform(val => val.trim()),
  
  description: z.string()
    .max(1000, "Description too long")
    .optional()
    .transform(val => val?.trim() || ""),
  
  category: documentCategorySchema.optional(),
  
  tags: z.array(tagSchema)
    .max(10, "Maximum 10 tags allowed")
    .default([])
    .transform(tags => 
      // Remove duplicates based on tag name
      tags.filter((tag, index, self) => 
        index === self.findIndex(t => t.name.toLowerCase() === tag.name.toLowerCase())
      )
    ),
  
  metadata: z.record(z.string(), z.any()).optional(),
})

// Type inference
export type EditDocumentFormData = z.infer<typeof editDocumentSchema>
export type DocumentCategory = z.infer<typeof documentCategorySchema>
export type DocumentTag = z.infer<typeof tagSchema>

// Category display names
export const categoryDisplayNames: Record<DocumentCategory, string> = {
  contracts: "Contracts",
  invoices: "Invoices",
  reports: "Reports",
  presentations: "Presentations",
  legal: "Legal Documents",
  financial: "Financial Documents",
  hr: "HR Documents",
  marketing: "Marketing Materials",
  technical: "Technical Documentation",
  other: "Other",
}

// Category icons (using Tabler icons)
export const categoryIcons: Record<DocumentCategory, string> = {
  contracts: "IconFileText",
  invoices: "IconFileInvoice",
  reports: "IconFileAnalytics",
  presentations: "IconPresentation",
  legal: "IconScale",
  financial: "IconCurrencyDollar",
  hr: "IconUsers",
  marketing: "IconSpeakerphone",
  technical: "IconCode",
  other: "IconFile",
}

// Helper to format tag for display
export function formatTag(tag: string): string {
  return tag.toLowerCase().replace(/[^a-z0-9-_]/g, '-')
}

// Helper to validate tag format
export function isValidTag(tag: string): boolean {
  return /^[a-zA-Z0-9-_]+$/.test(tag) && tag.length > 0 && tag.length <= 30
}

// Suggested tags based on category
export const suggestedTags: Partial<Record<DocumentCategory, string[]>> = {
  contracts: ["agreement", "nda", "lease", "employment", "vendor"],
  invoices: ["paid", "pending", "overdue", "recurring", "one-time"],
  reports: ["quarterly", "annual", "analysis", "summary", "detailed"],
  legal: ["confidential", "compliance", "regulatory", "policy"],
  financial: ["budget", "forecast", "audit", "tax", "expense"],
  hr: ["employee", "benefits", "policy", "recruitment", "training"],
}