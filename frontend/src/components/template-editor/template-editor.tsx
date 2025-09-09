"use client"

/**
 * Template Editor Component - Alfresco ECM Pattern
 * Provides temporary Google Docs editing for workflow templates
 */
import React, { useState, useCallback, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Loader2, Edit3, Save, X, Clock, ExternalLink, AlertCircle } from 'lucide-react'
import { toast } from 'sonner'
import { useUser } from '@clerk/nextjs'

interface EditSession {
  id: string
  template_id: string
  template_name: string
  google_doc_edit_url: string
  google_doc_url: string
  status: string
  created_at: string
  expires_at: string
  time_remaining_hours: number
  changes_detected?: boolean
}

interface Template {
  id: string
  name: string
  content: string
  description?: string
  category: string
  last_modified?: string
  modified_by?: string
}

interface TemplateEditorProps {
  template: Template
  onTemplateUpdated?: (template: Template) => void
  tenantId: string
}

export function TemplateEditor({ template, onTemplateUpdated, tenantId }: TemplateEditorProps) {
  const { user } = useUser()
  const [editSession, setEditSession] = useState<EditSession | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isCreatingSession, setIsCreatingSession] = useState(false)
  const [showInstructions, setShowInstructions] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Poll for session status updates
  useEffect(() => {
    if (editSession?.status === 'active') {
      const interval = setInterval(checkSessionStatus, 30000) // Check every 30 seconds
      return () => clearInterval(interval)
    }
  }, [editSession])

  const checkSessionStatus = useCallback(async () => {
    if (!editSession) return
    
    try {
      const response = await fetch(`/api/template-editor/sessions/${editSession.id}`)
      if (response.ok) {
        const updatedSession = await response.json()
        setEditSession(updatedSession)
      }
    } catch (error) {
      console.error('Failed to check session status:', error)
    }
  }, [editSession])

  const startEditing = async () => {
    if (!user) {
      toast.error('User authentication required')
      return
    }

    setIsCreatingSession(true)
    setError(null)

    try {
      const response = await fetch('/api/template-editor/sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          template_id: template.id,
          template_name: template.name,
          template_content: template.content,
          user_id: user.id,
          user_email: user.emailAddresses[0]?.emailAddress || '',
          tenant_id: tenantId
        })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to create editing session')
      }

      const session = await response.json()
      setEditSession(session)
      setShowInstructions(true)
      
      toast.success('Google Docs editing session created! Click "Open Editor" to start editing.')

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to start editing'
      setError(errorMessage)
      toast.error(errorMessage)
    } finally {
      setIsCreatingSession(false)
    }
  }

  const openEditor = () => {
    if (editSession?.google_doc_edit_url) {
      // Open Google Docs in new window
      const editorWindow = window.open(
        editSession.google_doc_edit_url,
        'googledocs',
        'width=1200,height=800,scrollbars=yes,resizable=yes'
      )
      
      if (editorWindow) {
        toast.success('Google Docs editor opened! Make your changes and return here to save.')
      } else {
        toast.error('Please allow popups to open the Google Docs editor')
      }
    }
  }

  const finishEditing = async () => {
    if (!editSession) return

    setIsLoading(true)
    setError(null)

    try {
      const response = await fetch(`/api/template-editor/sessions/${editSession.id}/finish`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          user_id: user?.id
        })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to finish editing session')
      }

      const result = await response.json()
      
      // Update local state
      setEditSession(null)
      setShowInstructions(false)
      
      if (result.changes_detected) {
        toast.success('Template updated successfully with your changes!')
        
        // Notify parent component of update
        if (onTemplateUpdated) {
          const updatedTemplate = { ...template, last_modified: new Date().toISOString() }
          onTemplateUpdated(updatedTemplate)
        }
      } else {
        toast.info('No changes detected. Template remains unchanged.')
      }

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to finish editing'
      setError(errorMessage)
      toast.error(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }

  const cancelEditing = async () => {
    if (!editSession) return

    setIsLoading(true)
    
    try {
      const response = await fetch(`/api/template-editor/sessions/${editSession.id}?user_id=${user?.id}`, {
        method: 'DELETE'
      })

      if (response.ok) {
        setEditSession(null)
        setShowInstructions(false)
        toast.info('Editing session cancelled')
      } else {
        throw new Error('Failed to cancel session')
      }
    } catch (error) {
      toast.error('Failed to cancel editing session')
    } finally {
      setIsLoading(false)
    }
  }

  const extendSession = async () => {
    if (!editSession) return

    try {
      const response = await fetch(`/api/template-editor/sessions/${editSession.id}/extend`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          user_id: user?.id,
          hours: 1
        })
      })

      if (response.ok) {
        const updatedSession = await response.json()
        setEditSession(updatedSession)
        toast.success('Session extended by 1 hour')
      } else {
        throw new Error('Failed to extend session')
      }
    } catch (error) {
      toast.error('Failed to extend session')
    }
  }

  const formatTimeRemaining = (hours: number): string => {
    if (hours < 1) {
      const minutes = Math.floor(hours * 60)
      return `${minutes}m`
    }
    return `${Math.floor(hours)}h ${Math.floor((hours % 1) * 60)}m`
  }

  return (
    <Card className="w-full max-w-4xl">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Edit3 className="h-5 w-5" />
              Template Editor
            </CardTitle>
            <CardDescription>
              Edit "{template.name}" using Google Docs integration
            </CardDescription>
          </div>
          
          <div className="flex items-center gap-2">
            <Badge variant="outline">{template.category}</Badge>
            {editSession && (
              <Badge 
                variant={editSession.status === 'active' ? 'default' : 'secondary'}
              >
                {editSession.status}
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {!editSession ? (
          // Not editing mode
          <div className="space-y-4">
            <div className="prose max-w-none">
              <div 
                className="p-4 border rounded-lg bg-gray-50"
                dangerouslySetInnerHTML={{ __html: template.content || '<p>No content</p>' }}
              />
            </div>
            
            <div className="flex items-center justify-between pt-4">
              <div className="text-sm text-gray-600">
                {template.last_modified && (
                  <span>Last modified: {new Date(template.last_modified).toLocaleString()}</span>
                )}
              </div>
              
              <Button 
                onClick={startEditing} 
                disabled={isCreatingSession}
                className="flex items-center gap-2"
              >
                {isCreatingSession ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Creating Session...
                  </>
                ) : (
                  <>
                    <Edit3 className="h-4 w-4" />
                    Edit with Google Docs
                  </>
                )}
              </Button>
            </div>
          </div>
        ) : (
          // Editing mode
          <div className="space-y-4">
            {showInstructions && (
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  <div className="space-y-2">
                    <p><strong>Editing Instructions:</strong></p>
                    <ol className="list-decimal list-inside space-y-1 text-sm">
                      <li>Click "Open Editor" to edit the template in Google Docs</li>
                      <li>Make your changes in Google Docs</li>
                      <li>Return here and click "Save Changes" when finished</li>
                      <li>The temporary Google Doc will be automatically deleted</li>
                    </ol>
                  </div>
                </AlertDescription>
              </Alert>
            )}

            <div className="flex items-center justify-between p-4 bg-blue-50 rounded-lg">
              <div className="flex items-center gap-3">
                <Clock className="h-5 w-5 text-blue-600" />
                <div>
                  <p className="font-medium">Active Editing Session</p>
                  <p className="text-sm text-gray-600">
                    Expires in: {formatTimeRemaining(editSession.time_remaining_hours || 0)}
                  </p>
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={extendSession}
                >
                  <Clock className="h-4 w-4 mr-1" />
                  Extend +1h
                </Button>
                
                <Button
                  onClick={openEditor}
                  className="flex items-center gap-2"
                >
                  <ExternalLink className="h-4 w-4" />
                  Open Editor
                </Button>
              </div>
            </div>

            <div className="flex items-center justify-between pt-4">
              <Button
                variant="outline"
                onClick={cancelEditing}
                disabled={isLoading}
                className="flex items-center gap-2"
              >
                <X className="h-4 w-4" />
                Cancel Editing
              </Button>
              
              <Button
                onClick={finishEditing}
                disabled={isLoading}
                className="flex items-center gap-2"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Saving Changes...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4" />
                    Save Changes
                  </>
                )}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}