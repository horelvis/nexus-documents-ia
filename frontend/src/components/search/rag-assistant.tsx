"use client"

import { useState } from "react"
import { 
  IconMessageCircle,
  IconSend,
  IconLoader2,
  IconFile,
  IconSparkles,
  IconInfoCircle
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"

interface RagAssistantProps {
  searchResults: any[]
  searchQuery: string
  onAskQuestion: (question: string) => Promise<void>
  agentResponse?: any
  isProcessing?: boolean
}

export function RagAssistant({ 
  searchResults, 
  searchQuery, 
  onAskQuestion,
  agentResponse,
  isProcessing = false
}: RagAssistantProps) {
  const [question, setQuestion] = useState("")
  
  const handleAskQuestion = () => {
    if (question.trim()) {
      onAskQuestion(question)
      setQuestion("")
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isProcessing) {
      handleAskQuestion()
    }
  }

  // Suggested questions based on search results
  const suggestedQuestions = [
    "What are the key points from these documents?",
    "Can you summarize the main findings?",
    "What patterns do you see in these documents?",
    `Tell me more about "${searchQuery}"`,
    "What are the most important details?"
  ]

  return (
    <div className="space-y-4">
      {/* Context Info */}
      <Card className="bg-purple-50 border-purple-200">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <IconMessageCircle className="h-5 w-5 text-purple-600" />
            Q&A Assistant
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            I can help you understand these {searchResults.length} documents. 
            Ask me anything about their content, and I'll provide detailed answers with sources.
          </p>
        </CardContent>
      </Card>

      {/* Question Input */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ask a Question</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Input
              placeholder="What would you like to know about these documents?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={isProcessing}
            />
            <Button 
              onClick={handleAskQuestion} 
              disabled={isProcessing || !question.trim()}
            >
              {isProcessing ? (
                <IconLoader2 className="h-4 w-4 animate-spin" />
              ) : (
                <IconSend className="h-4 w-4" />
              )}
            </Button>
          </div>

          {/* Suggested Questions */}
          <div>
            <p className="text-xs text-muted-foreground mb-2">Suggested questions:</p>
            <div className="flex flex-wrap gap-2">
              {suggestedQuestions.map((q, index) => (
                <Badge
                  key={index}
                  variant="outline"
                  className="cursor-pointer hover:bg-secondary"
                  onClick={() => {
                    setQuestion(q)
                    onAskQuestion(q)
                  }}
                >
                  {q}
                </Badge>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Processing State */}
      {isProcessing && (
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="py-8">
            <div className="flex flex-col items-center justify-center space-y-2">
              <IconSparkles className="h-8 w-8 text-blue-500 animate-pulse" />
              <p className="text-sm text-muted-foreground">Analyzing documents and generating answer...</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Document Context */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <IconFile className="h-4 w-4" />
            Document Context
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {searchResults.slice(0, 5).map((result, index) => (
              <div key={index} className="flex items-start gap-2 text-sm">
                <Badge variant="outline" className="mt-0.5">
                  {Math.round(result.score * 100)}%
                </Badge>
                <div className="flex-1">
                  <p className="font-medium">{result.document.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {result.document.description || result.highlights?.[0] || "No preview available"}
                  </p>
                </div>
              </div>
            ))}
            {searchResults.length > 5 && (
              <p className="text-xs text-muted-foreground text-center pt-2">
                And {searchResults.length - 5} more documents...
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Tips */}
      <Card className="bg-muted/50">
        <CardContent className="py-4">
          <div className="flex gap-2">
            <IconInfoCircle className="h-4 w-4 text-muted-foreground mt-0.5" />
            <div className="text-sm text-muted-foreground">
              <p className="font-medium">Tips for better answers:</p>
              <ul className="list-disc list-inside mt-1 space-y-0.5">
                <li>Be specific about what you want to know</li>
                <li>Ask about relationships between documents</li>
                <li>Request summaries or comparisons</li>
                <li>Ask for specific data points or facts</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}