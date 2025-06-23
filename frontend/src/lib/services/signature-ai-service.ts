import { apiClient } from '@/lib/api-client'

export interface DocumentAnalysis {
  document_type: string
  confidence: number
  suggested_fields: SignatureFieldSuggestion[]
  detected_zones: DetectedZone[]
  similar_documents: SimilarDocument[]
  learning_data: {
    patterns_used: number
    poi_detected: number
    suggestion_source: string
  }
}

export interface SignatureFieldSuggestion {
  type: 'signature' | 'date' | 'text' | 'name' | 'email'
  signer_role: string
  x: number
  y: number
  width: number
  height: number
  page: number
  confidence: number
  reason: string
  source: 'poi_detection' | 'learned_pattern' | 'defaults'
}

export interface DetectedZone {
  type: string
  bbox: [number, number, number, number]
  page: number
  confidence?: number
  text_nearby?: string
  role_hint?: string
}

export interface SimilarDocument {
  document_id: string
  title: string
  signed_at: string
  field_count: number
}

export interface PlacementFeedback {
  document_id: string
  document_type: string
  placed_fields: any[]
}

export interface SignerInfo {
  id: string
  email: string
  name: string
  role?: string
}

class SignatureAIService {
  async analyzeDocument(documentId: string, metadata?: any): Promise<DocumentAnalysis> {
    const response = await apiClient.post('/signatures/ai/analyze', {
      document_id: documentId,
      metadata
    })
    return response.data
  }

  async analyzeFile(file: File, metadata?: any): Promise<DocumentAnalysis> {
    const formData = new FormData()
    formData.append('file', file)
    if (metadata) {
      formData.append('metadata', JSON.stringify(metadata))
    }

    const response = await apiClient.post('/signatures/ai/analyze-file', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    return response.data
  }

  async learnFromPlacement(feedback: PlacementFeedback): Promise<void> {
    await apiClient.post('/signatures/ai/learn', feedback)
  }

  async suggestPlacements(
    documentId: string, 
    signers: SignerInfo[], 
    documentAnalysis?: DocumentAnalysis
  ): Promise<{
    document_type: string
    suggested_fields: any[]
    confidence: number
  }> {
    const response = await apiClient.post('/signatures/ai/suggest-placements', {
      document_id: documentId,
      signers,
      document_analysis: documentAnalysis
    })
    return response.data
  }

  async getLearnedPatterns(documentType: string): Promise<any> {
    const response = await apiClient.get(`/signatures/ai/patterns/${documentType}`)
    return response.data
  }

  async getDocumentTypes(): Promise<any> {
    const response = await apiClient.get('/signatures/ai/document-types')
    return response.data
  }

  // Helper method to convert AI suggestions to placement editor format
  convertSuggestionsToFields(
    suggestions: SignatureFieldSuggestion[], 
    signers: Array<{ id: string; name: string; email: string; color: string }>
  ): any[] {
    return suggestions.map((suggestion, index) => {
      // Match signer by role or use index
      const signerIndex = suggestion.signer_role.includes('party_') 
        ? parseInt(suggestion.signer_role.split('_')[1]) - 1
        : index % signers.length
      
      const signer = signers[signerIndex] || signers[0]
      
      return {
        id: `ai-field-${index}`,
        type: suggestion.type,
        signer: signer.id,
        x: suggestion.x,
        y: suggestion.y,
        width: suggestion.width,
        height: suggestion.height,
        page: suggestion.page,
        required: true,
        label: this.getFieldLabel(suggestion.type, signer.name),
        confidence: suggestion.confidence,
        aiSuggested: true,
        source: suggestion.source,
        reason: suggestion.reason
      }
    })
  }

  async generateSignatureMessage(documentTitle: string, signerCount: number, documentType?: string): Promise<string> {
    try {
      const response = await apiClient.post('/signatures/ai/generate-message', {
        document_title: documentTitle,
        signer_count: signerCount,
        document_type: documentType
      })
      
      if (response.data?.message) {
        return response.data.message
      }
      
      // Fallback message if API fails
      return this.generateFallbackMessage(documentTitle, signerCount)
    } catch (error) {
      console.error('Failed to generate AI message:', error)
      return this.generateFallbackMessage(documentTitle, signerCount)
    }
  }
  
  private generateFallbackMessage(documentTitle: string, signerCount: number): string {
    const signerText = signerCount === 1 ? 'signature' : 'signatures'
    return `Hello,\n\nI'm requesting your signature on "${documentTitle}". Please review the document and sign where indicated.\n\nThis document requires ${signerCount} ${signerText}. You'll receive a confirmation once all parties have signed.\n\nThank you for your prompt attention to this matter.`
  }
  
  private getFieldLabel(type: string, signerName: string): string {
    const labels = {
      signature: `${signerName} Signature`,
      date: 'Date',
      name: `${signerName} Name`,
      email: `${signerName} Email`,
      text: 'Text Field'
    }
    return labels[type] || 'Field'
  }
}

export const signatureAIService = new SignatureAIService()

// Hook for using the AI service
import { useState } from 'react'
import { useAuth } from '@clerk/nextjs'

export function useSignatureAI() {
  const { getToken } = useAuth()
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<DocumentAnalysis | null>(null)
  const [error, setError] = useState<string | null>(null)

  const analyzeDocument = async (documentId: string, metadata?: any) => {
    setIsAnalyzing(true)
    setError(null)
    
    try {
      const token = await getToken()
      if (!token) throw new Error('Not authenticated')
      
      const result = await signatureAIService.analyzeDocument(documentId, metadata)
      setAnalysis(result)
      return result
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Analysis failed'
      setError(message)
      throw err
    } finally {
      setIsAnalyzing(false)
    }
  }

  const suggestPlacements = async (
    documentId: string,
    signers: SignerInfo[],
    existingAnalysis?: DocumentAnalysis
  ) => {
    try {
      const token = await getToken()
      if (!token) throw new Error('Not authenticated')
      
      return await signatureAIService.suggestPlacements(
        documentId, 
        signers, 
        existingAnalysis || analysis || undefined
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Suggestion failed'
      setError(message)
      throw err
    }
  }

  const learnFromPlacement = async (feedback: PlacementFeedback) => {
    try {
      const token = await getToken()
      if (!token) throw new Error('Not authenticated')
      
      await signatureAIService.learnFromPlacement(feedback)
    } catch (err) {
      // Learning failures shouldn't interrupt the user flow
      console.error('Failed to submit learning data:', err)
    }
  }
  
  const generateMessage = async (documentTitle: string, signerCount: number, documentType?: string) => {
    try {
      const token = await getToken()
      if (!token) throw new Error('Not authenticated')
      
      return await signatureAIService.generateSignatureMessage(documentTitle, signerCount, documentType)
    } catch (err) {
      console.error('Failed to generate AI message:', err)
      // Return fallback message
      return signatureAIService['generateFallbackMessage'](documentTitle, signerCount)
    }
  }

  return {
    analyzeDocument,
    suggestPlacements,
    learnFromPlacement,
    generateMessage,
    isAnalyzing,
    analysis,
    error,
    signatureAIService
  }
}