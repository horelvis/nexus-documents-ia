"use client"

import { useState, useEffect } from "react"
import { 
  IconRobot, 
  IconMessageCircle, 
  IconSend, 
  IconLoader2,
  IconBulb,
  IconChevronUp,
  IconChevronDown
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"
import { useSearchService, SearchResult } from "@/lib/services/search.service"
import { useNotifications } from "@/contexts/notifications-context"

interface RAGAssistantProps {
  searchResults: SearchResult[]
  searchQuery: string
  onSuggestionClick: (suggestion: string) => void
}

interface ChatMessage {
  type: 'user' | 'assistant'
  content: string
  timestamp: Date
}

export default function RAGAssistant({ 
  searchResults, 
  searchQuery, 
  onSuggestionClick 
}: RAGAssistantProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [currentInput, setCurrentInput] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])

  const { addNotification } = useNotifications()
  const searchService = useSearchService()

  // Generate contextual suggestions based on search results
  useEffect(() => {
    console.log('RAG Assistant - Search results:', searchResults.length, 'Query:', searchQuery)
    if (searchResults.length > 0) {
      generateSuggestions()
    }
  }, [searchResults, searchQuery])

  const generateSuggestions = () => {
    const fileTypes = [...new Set(searchResults.map(r => r.document.file_type))]
    const docCount = searchResults.length
    const query = searchQuery.toLowerCase()
    
    let contextualSuggestions: string[] = []

    // Context-aware suggestions based on search query
    if (query.includes('factura') || query.includes('invoice') || query.includes('bill')) {
      contextualSuggestions = [
        `¿Cuál es el total de las facturas encontradas?`,
        `¿Hay facturas pendientes de pago?`,
        `Analiza los proveedores de estas facturas`,
        `¿Cuándo vencen estas facturas?`
      ]
    } else if (query.includes('contrato') || query.includes('contract') || query.includes('agreement')) {
      contextualSuggestions = [
        `¿Cuándo expiran estos contratos?`,
        `Resume las condiciones principales`,
        `¿Hay cláusulas de renovación automática?`,
        `Identifica riesgos legales en estos contratos`
      ]
    } else if (query.includes('financi') || query.includes('budget') || query.includes('presupuesto')) {
      contextualSuggestions = [
        `Analiza el rendimiento financiero`,
        `¿Cuáles son las tendencias principales?`,
        `Compara ingresos vs gastos`,
        `Identifica oportunidades de ahorro`
      ]
    } else if (query.includes('legal') || query.includes('compliance') || query.includes('regulation')) {
      contextualSuggestions = [
        `¿Hay riesgos de cumplimiento?`,
        `Analiza el estado de conformidad`,
        `¿Qué acciones correctivas se necesitan?`,
        `Resume los requisitos legales`
      ]
    } else {
      // Generic suggestions
      contextualSuggestions = [
        `Resume los ${docCount} documentos encontrados`,
        `¿Cuáles son los puntos clave?`,
        `Compara estos documentos entre sí`,
        `¿Qué patrones encuentras?`
      ]
    }

    // Add file-type specific suggestions if generic
    if (!query.includes('factura') && !query.includes('contrato')) {
      if (fileTypes.includes('pdf')) {
        contextualSuggestions.push('Analiza los documentos PDF encontrados')
      }
      if (fileTypes.includes('xlsx') || fileTypes.includes('csv')) {
        contextualSuggestions.push('Extrae datos de las hojas de cálculo')
      }
      if (fileTypes.includes('docx')) {
        contextualSuggestions.push('Resume los documentos de texto')
      }
    }

    setSuggestions(contextualSuggestions.slice(0, 4))
  }

  const sendMessage = async (message: string) => {
    if (!message.trim()) return

    setIsProcessing(true)
    
    // Add user message
    const userMessage: ChatMessage = {
      type: 'user',
      content: message,
      timestamp: new Date()
    }
    setMessages(prev => [...prev, userMessage])
    setCurrentInput('')

    try {
      const response = await searchService.askDocuments({
        question: message,
        doc_ids: searchResults.map(r => r.document.id)
      })

      if (response.error) {
        addNotification({
          type: 'error',
          title: 'Error',
          message: response.error
        })
      } else if (response.data) {
        const assistantMessage: ChatMessage = {
          type: 'assistant',
          content: response.data.answer,
          timestamp: new Date()
        }
        setMessages(prev => [...prev, assistantMessage])
      }
    } catch (err) {
      addNotification({
        type: 'error',
        title: 'Error',
        message: 'Failed to get response from assistant'
      })
    } finally {
      setIsProcessing(false)
    }
  }

  const handleSuggestionClick = async (suggestion: string) => {
    // If it's a search term, don't expand - let parent handle search
    if (suggestion === "facturas" || suggestion === "contratos" || suggestion === "documentos") {
      onSuggestionClick(suggestion)
      return
    }
    
    // For questions/analysis, expand and send message
    setIsExpanded(true)
    onSuggestionClick(suggestion)
    // Small delay to ensure expansion animation completes
    setTimeout(() => {
      sendMessage(suggestion)
    }, 100)
  }

  // Show assistant even with 0 results to help guide users

  return (
    <Card className="border-blue-200 bg-blue-50/50 dark:bg-blue-950/20 dark:border-blue-800">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-blue-700 dark:text-blue-300">
            <IconRobot className="h-5 w-5" />
            AI Assistant
          </CardTitle>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-blue-600 hover:text-blue-700 dark:text-blue-400"
          >
            {isExpanded ? (
              <IconChevronUp className="h-4 w-4" />
            ) : (
              <IconChevronDown className="h-4 w-4" />
            )}
          </Button>
        </div>
        
        {!isExpanded && (
          <div className="space-y-2">
            <p className="text-sm text-blue-600 dark:text-blue-400">
              {searchResults.length === 0 ? (
                `No encontré documentos para "${searchQuery}". ¿Te ayudo a buscar algo más específico?`
              ) : (
                `Encontré ${searchResults.length} documento${searchResults.length !== 1 ? 's' : ''}. ¿Te ayudo a analizarlos?`
              )}
            </p>
            
            {searchResults.length > 0 ? (
              <div className="flex items-center justify-between">
                <div className="flex flex-wrap gap-1">
                  {[...new Set(searchResults.map(r => r.document.file_type).filter(type => type))].map(type => (
                    <Badge key={type} variant="outline" className="text-xs border-blue-200 text-blue-600 dark:border-blue-700 dark:text-blue-400">
                      {type?.toUpperCase() || 'UNKNOWN'}
                    </Badge>
                  ))}
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleSuggestionClick(`Resume los ${searchResults.length} documentos encontrados`)}
                  className="ml-2 h-6 text-xs border-blue-200 text-blue-600 hover:bg-blue-100 dark:border-blue-700 dark:text-blue-300 dark:hover:bg-blue-900/30"
                >
                  <IconBulb className="h-3 w-3 mr-1" />
                  Analizar
                </Button>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleSuggestionClick("pdf")}
                  className="h-6 text-xs border-blue-200 text-blue-600 hover:bg-blue-100 dark:border-blue-700 dark:text-blue-300 dark:hover:bg-blue-900/30"
                >
                  pdf
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleSuggestionClick("docx")}
                  className="h-6 text-xs border-blue-200 text-blue-600 hover:bg-blue-100 dark:border-blue-700 dark:text-blue-300 dark:hover:bg-blue-900/30"
                >
                  docx
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleSuggestionClick("imagen")}
                  className="h-6 text-xs border-blue-200 text-blue-600 hover:bg-blue-100 dark:border-blue-700 dark:text-blue-300 dark:hover:bg-blue-900/30"
                >
                  imagen
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleSuggestionClick("texto")}
                  className="h-6 text-xs border-blue-200 text-blue-600 hover:bg-blue-100 dark:border-blue-700 dark:text-blue-300 dark:hover:bg-blue-900/30"
                >
                  texto
                </Button>
              </div>
            )}
          </div>
        )}
      </CardHeader>

      {isExpanded && (
        <CardContent className="space-y-4">
          {/* Quick Suggestions */}
          {suggestions.length > 0 && messages.length === 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium text-blue-700 dark:text-blue-300">
                <IconBulb className="h-4 w-4" />
                Suggested Questions:
              </div>
              <div className="flex flex-wrap gap-2">
                {suggestions.map((suggestion, index) => (
                  <Button
                    key={index}
                    variant="outline"
                    size="sm"
                    onClick={() => handleSuggestionClick(suggestion)}
                    className="text-xs h-auto py-1 px-2 border-blue-200 text-blue-700 hover:bg-blue-100 dark:border-blue-700 dark:text-blue-300 dark:hover:bg-blue-900/30"
                  >
                    {suggestion}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* Chat Messages */}
          {messages.length > 0 && (
            <div className="space-y-3 max-h-64 overflow-y-auto">
              {messages.map((message, index) => (
                <div
                  key={index}
                  className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] rounded-lg p-3 text-sm ${
                      message.type === 'user'
                        ? 'bg-blue-600 text-white'
                        : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{message.content}</p>
                    <span className="text-xs opacity-70 mt-1 block">
                      {message.timestamp.toLocaleTimeString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Processing Indicator */}
          {isProcessing && (
            <div className="flex items-center gap-2 text-blue-600 dark:text-blue-400">
              <IconLoader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Analyzing documents...</span>
            </div>
          )}

          {/* Input */}
          <div className="flex gap-2">
            <Textarea
              placeholder="Ask me anything about these documents..."
              value={currentInput}
              onChange={(e) => setCurrentInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  sendMessage(currentInput)
                }
              }}
              rows={2}
              className="resize-none"
              disabled={isProcessing}
            />
            <Button
              onClick={() => sendMessage(currentInput)}
              disabled={isProcessing || !currentInput.trim()}
              size="sm"
              className="self-end"
            >
              <IconSend className="h-4 w-4" />
            </Button>
          </div>

          {/* Context Info */}
          <div className="text-xs text-blue-600/70 dark:text-blue-400/70 flex items-center gap-1">
            <IconMessageCircle className="h-3 w-3" />
            Analyzing {searchResults.length} documents from your search results
          </div>
        </CardContent>
      )}
    </Card>
  )
}