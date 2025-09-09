"use client"

import { useState, useEffect, use } from "react"
import { useBackendUser } from "@/contexts/user-context"
import Link from "next/link"
import { 
  IconFileText, 
  IconEdit,
  IconPlus,
  IconClock,
  IconUser,
  IconCheck
} from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useToast } from "@/hooks/use-toast"

interface Template {
  id: string
  name: string
  description: string
  content: string
  category: string
  created_at: string
  updated_at: string
  is_active: boolean
}

export default function TemplatesPage({ params }: { params: Promise<{ tenantId: string }> }) {
  const resolvedParams = use(params)
  const { backendUser } = useBackendUser()
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(true)
  const [templates, setTemplates] = useState<Template[]>([])
  const [editingSessions, setEditingSessions] = useState<Set<string>>(new Set())

  // Mock templates for demo - in production these would come from API
  const mockTemplates: Template[] = [
    {
      id: "123e4567-e89b-12d3-a456-426614174000",
      name: "Employee Contract Template",
      description: "Standard employment contract with customizable fields for salary, position, and benefits.",
      content: "<h1>Employment Contract</h1><p>This contract is between <strong>[COMPANY_NAME]</strong> and <strong>[EMPLOYEE_NAME]</strong>.</p><p>Position: <strong>[POSITION]</strong></p><ul><li>Salary: [SALARY]</li><li>Start Date: [START_DATE]</li><li>Benefits: [BENEFITS]</li></ul>",
      category: "HR",
      created_at: "2024-01-15",
      updated_at: "2024-01-15",
      is_active: true
    },
    {
      id: "456e7890-e89b-12d3-a456-426614174001",
      name: "Service Agreement Template",
      description: "Professional services agreement template with scope, timeline, and payment terms.",
      content: "<h1>Service Agreement</h1><p>Agreement between <strong>[CLIENT_NAME]</strong> and <strong>[PROVIDER_NAME]</strong></p><h2>Scope of Work</h2><p>[SCOPE_DESCRIPTION]</p><h2>Timeline</h2><p>Start: [START_DATE]<br>End: [END_DATE]</p><h2>Payment Terms</h2><p>Total: [TOTAL_AMOUNT]<br>Payment Schedule: [PAYMENT_TERMS]</p>",
      category: "Legal",
      created_at: "2024-01-10",
      updated_at: "2024-01-12",
      is_active: true
    },
    {
      id: "789e0123-e89b-12d3-a456-426614174002",
      name: "Invoice Template",
      description: "Professional invoice template with itemized billing and payment information.",
      content: "<h1>Invoice</h1><p><strong>From:</strong> [COMPANY_NAME]<br><strong>To:</strong> [CLIENT_NAME]</p><p><strong>Invoice Number:</strong> [INVOICE_NUMBER]<br><strong>Date:</strong> [INVOICE_DATE]<br><strong>Due Date:</strong> [DUE_DATE]</p><h2>Items</h2><table><tr><th>Description</th><th>Quantity</th><th>Price</th><th>Total</th></tr><tr><td>[ITEM_1]</td><td>[QTY_1]</td><td>[PRICE_1]</td><td>[TOTAL_1]</td></tr></table><p><strong>Total Amount:</strong> [TOTAL_AMOUNT]</p>",
      category: "Finance",
      created_at: "2024-01-08",
      updated_at: "2024-01-14",
      is_active: true
    }
  ]

  const loadData = async () => {
    setIsLoading(true)
    try {
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 500))
      setTemplates(mockTemplates)
    } catch (error) {
      console.error('Error loading templates:', error)
      toast({
        title: "Error",
        description: "Failed to load templates",
        variant: "destructive"
      })
    } finally {
      setIsLoading(false)
    }
  }

  const startEditing = async (template: Template) => {
    setEditingSessions(prev => new Set([...prev, template.id]))
    
    try {
      const requestBody = {
        template_id: template.id,
        template_name: template.name,
        template_content: template.content,
        user_id: backendUser?.id || backendUser?.clerk_user_id || "anonymous",
        user_email: backendUser?.email || "user@example.com",
        tenant_id: resolvedParams.tenantId
      }
      
      // Debug logging
      console.log('👤 Frontend - Backend user object:', backendUser)
      console.log('🔑 Frontend - Sending user_id:', requestBody.user_id)
      console.log('📧 Frontend - Sending user_email:', requestBody.user_email)
      console.log('🏢 Frontend - Sending tenant_id:', requestBody.tenant_id)
      
      const response = await fetch(`/api/template-editor/sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody)
      })

      if (!response.ok) {
        throw new Error('Failed to create edit session')
      }

      const session = await response.json()
      
      toast({
        title: "Edit Session Created",
        description: "Opening Google Docs for editing...",
      })

      // Open Google Docs in new tab
      window.open(session.google_doc_edit_url, '_blank')
      
      // Show instructions
      setTimeout(() => {
        toast({
          title: "Editing Instructions",
          description: `Edit the document in Google Docs. Session expires at ${new Date(session.expires_at).toLocaleTimeString()}`,
        })
      }, 1000)

    } catch (error) {
      console.error('Error starting edit session:', error)
      toast({
        title: "Error",
        description: "Failed to start editing session",
        variant: "destructive"
      })
    } finally {
      setEditingSessions(prev => {
        const newSet = new Set(prev)
        newSet.delete(template.id)
        return newSet
      })
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  if (isLoading) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex justify-center items-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Document Templates</h1>
          <p className="text-muted-foreground">
            Manage and edit document templates with Google Docs integration
          </p>
        </div>
        <Button>
          <IconPlus className="w-4 h-4 mr-2" />
          New Template
        </Button>
      </div>

      {/* Templates Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {templates.map((template) => (
          <Card key={template.id} className="h-full">
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="flex items-center space-x-2">
                  <IconFileText className="w-5 h-5 text-primary" />
                  <CardTitle className="text-lg">{template.name}</CardTitle>
                </div>
                <Badge variant="outline">{template.category}</Badge>
              </div>
              <CardDescription className="line-clamp-2">
                {template.description}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Template Preview */}
              <div className="bg-muted rounded-md p-3 text-sm max-h-32 overflow-hidden">
                <div 
                  className="line-clamp-4 text-muted-foreground"
                  dangerouslySetInnerHTML={{ 
                    __html: template.content.replace(/<[^>]*>/g, '').substring(0, 150) + '...'
                  }}
                />
              </div>

              {/* Template Info */}
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <div className="flex items-center space-x-1">
                  <IconClock className="w-3 h-3" />
                  <span>Updated {new Date(template.updated_at).toLocaleDateString()}</span>
                </div>
                {template.is_active && (
                  <div className="flex items-center space-x-1 text-green-600">
                    <IconCheck className="w-3 h-3" />
                    <span>Active</span>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex space-x-2">
                <Button
                  onClick={() => startEditing(template)}
                  disabled={editingSessions.has(template.id)}
                  className="flex-1"
                >
                  {editingSessions.has(template.id) ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Creating Session...
                    </>
                  ) : (
                    <>
                      <IconEdit className="w-4 h-4 mr-2" />
                      Edit Template
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Help Section */}
      <Card className="mt-8">
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <IconUser className="w-5 h-5" />
            <span>How Template Editing Works</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>1. Click "Edit Template" to create a temporary Google Docs session</p>
          <p>2. Edit the document in Google Docs with full formatting support</p>
          <p>3. Your changes are automatically saved to Google Docs</p>
          <p>4. When finished, return here and finalize your session to sync changes</p>
          <p>5. Temporary documents are automatically cleaned up after 4 hours</p>
        </CardContent>
      </Card>
    </div>
  )
}