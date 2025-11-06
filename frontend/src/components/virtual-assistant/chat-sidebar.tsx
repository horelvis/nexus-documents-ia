"use client"

import { useState, useRef, useEffect } from "react"
import { Send, X, Bot, User, Loader2, Paperclip, Mic, MoreVertical, Trash2, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { cn } from "@/lib/utils"
import { Card } from "@/components/ui/card"
import Link from "next/link"
import ReactMarkdown from "react-markdown"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useVirtualAssistant } from "@/contexts/virtual-assistant-context"
import { useUpload } from "@/contexts/upload-context"
import { useRouter, usePathname } from "next/navigation"

interface ChatSidebarProps {
  isOpen: boolean
  onClose: () => void
}

export function ChatSidebar({ isOpen, onClose }: ChatSidebarProps) {
  const {
    currentConversation,
    isLoading,
    isStreaming,
    error,
    sendMessage,
    clearConversation,
    createNewConversation,
    loadWelcomeMessage,
  } = useVirtualAssistant()
  
  const [input, setInput] = useState("")
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { setUploadDialogOpen } = useUpload()
  const router = useRouter()
  const pathname = usePathname()

  // Track if we've loaded welcome for current conversation
  const [welcomeLoaded, setWelcomeLoaded] = useState(false)
  
  useEffect(() => {
    console.log("ChatSidebar useEffect triggered", { 
      isOpen, 
      hasConversation: !!currentConversation,
      messageCount: currentConversation?.messages?.length,
      welcomeLoaded
    })
    
    if (isOpen) {
      if (!currentConversation) {
        console.log("Creating new conversation...")
        // Create new conversation if none exists
        createNewConversation()
        setWelcomeLoaded(false) // Reset welcome loaded flag
      } else if (currentConversation.messages.length === 0 && !welcomeLoaded && !isLoading) {
        console.log("Loading welcome message...")
        // Load welcome message if conversation is empty
        setWelcomeLoaded(true) // Mark as loading/loaded to prevent multiple calls
        loadWelcomeMessage()
      } else {
        console.log("Conversation already has messages or welcome already loaded:", currentConversation.messages.length)
      }
    }
  }, [isOpen, currentConversation, createNewConversation, loadWelcomeMessage, welcomeLoaded, isLoading])

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus()
    }
  }, [isOpen])

  // Autoscroll to bottom when new messages arrive or when loading/streaming
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [currentConversation?.messages, isLoading, isStreaming])

  const handleSend = async () => {
    if (!input.trim() || isLoading) return
    
    const message = input
    setInput("")
    await sendMessage(message)
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    
    // Reset height to auto to get proper scrollHeight
    e.target.style.height = 'auto'
    // Set height based on scrollHeight, with min and max limits
    const newHeight = Math.min(Math.max(e.target.scrollHeight, 40), 120)
    e.target.style.height = `${newHeight}px`
  }

  return (
    <div
      className={cn(
        "fixed right-0 top-0 h-full w-[480px] bg-background border-l shadow-xl",
        "transform transition-transform duration-300 ease-in-out z-50",
        isOpen ? "translate-x-0" : "translate-x-full"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b bg-primary/5">
        <div className="flex items-center gap-3">
          <Avatar className="h-10 w-10">
            <AvatarImage src="/assistant-avatar.png" />
            <AvatarFallback className="bg-primary text-primary-foreground">
              <Bot className="h-5 w-5" />
            </AvatarFallback>
          </Avatar>
          <div>
            <h3 className="font-semibold">Asistente Virtual</h3>
            <p className="text-xs text-muted-foreground">
              {isLoading ? "Escribiendo..." : "Siempre disponible"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={createNewConversation}
            className="h-8 w-8"
            title="Nueva conversación"
          >
            <Plus className="h-4 w-4" />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={clearConversation}>
                <Trash2 className="h-4 w-4 mr-2" />
                Limpiar chat
              </DropdownMenuItem>
              <DropdownMenuItem>Configuración</DropdownMenuItem>
              <DropdownMenuItem>Ayuda</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="h-8 w-8"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 h-[calc(100vh-140px)] p-4" ref={scrollAreaRef}>
        <div className="space-y-4">
          {currentConversation?.messages.map((message) => {
            // Don't render streaming messages that are empty
            if (message.isStreaming && !message.content) {
              return null
            }
            
            return (
              <div
                key={message.id}
                className={cn(
                  "flex gap-3",
                  message.role === "user" && "flex-row-reverse"
                )}
              >
                <Avatar className="h-8 w-8 flex-shrink-0">
                  {message.role === "assistant" ? (
                    <>
                      <AvatarImage src="/assistant-avatar.png" />
                      <AvatarFallback className="bg-primary text-primary-foreground">
                        <Bot className="h-4 w-4" />
                      </AvatarFallback>
                    </>
                  ) : (
                    <AvatarFallback className="bg-secondary">
                      <User className="h-4 w-4" />
                    </AvatarFallback>
                  )}
                </Avatar>
                <Card
                  className={cn(
                    "max-w-[85%] px-4 py-2",
                    message.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted"
                  )}
                >
                  <div className="text-sm prose prose-sm dark:prose-invert max-w-none">
                    {message.role === "assistant" ? (
                      <ReactMarkdown
                        components={{
                          a: ({ href, children }) => {
                            // Handle internal links
                            if (href?.startsWith('/')) {
                              return (
                                <Link 
                                  href={href} 
                                  className="text-primary hover:underline font-medium"
                                  onClick={(e) => {
                                    // Navigate without closing chat
                                    e.preventDefault()
                                    router.push(href)
                                    // Don't close the chat to maintain context
                                  }}
                                >
                                  {children}
                                </Link>
                              )
                            }
                            // External links
                            return (
                              <a 
                                href={href} 
                                target="_blank" 
                                rel="noopener noreferrer"
                                className="text-primary hover:underline"
                              >
                                {children}
                              </a>
                            )
                          },
                          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                          ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
                          ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
                          li: ({ children }) => <li className="text-sm leading-relaxed">{children}</li>,
                          h1: ({ children }) => <h1 className="text-lg font-bold mb-3 text-primary">{children}</h1>,
                          h2: ({ children }) => <h2 className="text-base font-semibold mb-2 text-primary border-b border-border pb-1">{children}</h2>,
                          h3: ({ children }) => <h3 className="text-sm font-semibold mb-2 text-foreground">{children}</h3>,
                          strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
                          em: ({ children }) => <em className="italic">{children}</em>,
                          code: ({ children }) => (
                            <code className="bg-muted px-1 py-0.5 rounded text-xs font-mono border">
                              {children}
                            </code>
                          ),
                          blockquote: ({ children }) => (
                            <blockquote className="border-l-4 border-primary pl-3 my-2 text-muted-foreground italic">
                              {children}
                            </blockquote>
                          ),
                        }}
                      >
                        {message.content || (message.isStreaming ? "..." : "")}
                      </ReactMarkdown>
                    ) : (
                      <p className="whitespace-pre-wrap">
                        {message.content || (message.isStreaming ? "..." : "")}
                      </p>
                    )}
                  </div>
                  <p
                    className={cn(
                      "text-xs mt-1 opacity-70",
                      message.role === "user" ? "text-primary-foreground" : "text-muted-foreground"
                    )}
                  >
                    {message.timestamp.toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                </Card>
              </div>
            )
          })}
          {isLoading && !isStreaming && (
            <div className="flex gap-3">
              <Avatar className="h-8 w-8">
                <AvatarImage src="/assistant-avatar.png" />
                <AvatarFallback className="bg-primary text-primary-foreground">
                  <Bot className="h-4 w-4" />
                </AvatarFallback>
              </Avatar>
              <Card className="px-4 py-2 bg-muted">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
                </div>
              </Card>
            </div>
          )}
          {error && (
            <div className="text-center text-sm text-red-500 bg-red-50 dark:bg-red-900/20 p-2 rounded">
              {error}
            </div>
          )}
          {/* Scroll anchor */}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t p-4 bg-background">
        <div className="flex gap-2">
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-10 w-10"
            onClick={() => setUploadDialogOpen(true)}
            title="Subir documento"
          >
            <Paperclip className="h-4 w-4" />
          </Button>
          <Textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyPress={handleKeyPress}
            placeholder="Escribe tu mensaje... (Shift+Enter para nueva línea)"
            className="flex-1 min-h-[40px] max-h-[120px] resize-none"
            disabled={isLoading}
            rows={1}
          />
          <Button variant="ghost" size="icon" className="h-10 w-10">
            <Mic className="h-4 w-4" />
          </Button>
          <Button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            size="icon"
            className="h-10 w-10"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-2 text-center">
          Enter para enviar • Shift+Enter para nueva línea
        </p>
      </div>
    </div>
  )
}