"use client"

import React, { useEffect, useState, useRef } from "react"
import { useSearchParams } from "next/navigation"
import { 
  MessageSquare, 
  Settings, 
  Zap, 
  Brain, 
  RefreshCw
} from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

import { ElysiaChat, type ElysiaChatRef } from "@/components/elysia-chat"
import { useBackendUser } from "@/contexts/user-context"
import { useTranslation } from "@/lib/i18n/hooks"

interface ChatPageProps {
  params: Promise<{
    tenantId: string
  }>
}

export default function ChatPage({ params }: ChatPageProps) {
  const { tenantId } = React.use(params)
  
  const { backendUser } = useBackendUser()
  const searchParams = useSearchParams()
  const [mode, setMode] = useState<"chat" | "settings">("chat")
  const [randomPrompts, setRandomPrompts] = useState<string[]>([])
  const [hasStartedChat, setHasStartedChat] = useState(false)
  const [initialQuery, setInitialQuery] = useState<string | null>(null)
  const [documentContext, setDocumentContext] = useState<{ id: string; name: string } | null>(null)
  const elysiaChatRef = useRef<ElysiaChatRef>(null)
  const { t } = useTranslation()

  // Get prompts - simple function, no useCallback needed
  const getRandomPrompts = (count: number = 4): string[] => {
    const prompts = [
      t('chatPage.examplePrompts.0'),
      t('chatPage.examplePrompts.1'),
      t('chatPage.examplePrompts.2'),
      t('chatPage.examplePrompts.3'),
      t('chatPage.examplePrompts.4'),
      t('chatPage.examplePrompts.5'),
      t('chatPage.examplePrompts.6'),
      t('chatPage.examplePrompts.7')
    ]
    const shuffled = [...prompts].sort(() => 0.5 - Math.random())
    return shuffled.slice(0, count)
  }

  useEffect(() => {
    const queryParam = searchParams.get('q')
    const documentId = searchParams.get('documentId')
    const documentName = searchParams.get('documentName')

    if (documentId && documentName) {
      // User came from document list - set document context and simple prompt
      const decodedName = decodeURIComponent(documentName)
      setDocumentContext({ id: documentId, name: decodedName })
      // Simple user-visible prompt
      setInitialQuery(`Analiza el documento "${decodedName}"`)
      setHasStartedChat(true)
    } else if (queryParam) {
      setInitialQuery(queryParam)
      setHasStartedChat(true)
    }
  }, [searchParams])

  // Initialize prompts once on mount
  useEffect(() => {
    setRandomPrompts(getRandomPrompts(4))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const refreshPrompts = () => {
    setRandomPrompts(getRandomPrompts(4))
  }

  const handlePromptClick = (prompt: string) => {
    setHasStartedChat(true)
    if (elysiaChatRef.current) {
      elysiaChatRef.current.sendQuery(prompt)
    }
  }

  return (
    <div className="flex flex-col w-full h-screen overflow-hidden">
      {/* Header */}
      <div className="flex w-full justify-between items-center sticky top-0 z-20 p-4 bg-background border-b">
        <div className="flex items-center gap-4">
          <Brain className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-xl font-semibold">{t('chatPage.assistantName')}</h1>
            <p className="text-sm text-muted-foreground">
              {t('chatPage.assistantSubtitle')}
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {/* Mode Selector */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                {mode === "chat" ? (
                  <>
                    <MessageSquare className="h-4 w-4 mr-2" />
                    {t('chatPage.mode.chat')}
                  </>
                ) : (
                  <>
                    <Settings className="h-4 w-4 mr-2" />
                    {t('chatPage.mode.settings')}
                  </>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onClick={() => setMode("chat")}>
                <MessageSquare className="h-4 w-4 mr-2" />
                {t('chatPage.mode.chat')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setMode("settings")}>
                <Settings className="h-4 w-4 mr-2" />
                {t('chatPage.mode.settings')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          
          <Badge variant="secondary">
            <Zap className="h-3 w-3 mr-1" />
            {t('chatPage.status.online')}
          </Badge>
        </div>
      </div>

      {mode === "chat" ? (
        <div className="flex flex-col w-full flex-1 min-h-0">
          {!hasStartedChat ? (
            <div className="flex flex-col items-center justify-center flex-1 p-6 overflow-y-auto">
              <div className="text-center mb-8">
                <h2 className="text-3xl font-bold mb-2">{t('chatPage.landingScreen.askEmma')}</h2>
                <p className="text-muted-foreground">
                  {t('chatPage.landingScreen.askEmmaSubtitle')}
                </p>
              </div>

              <div className="flex items-center gap-4 mb-6">
                <h3 className="text-lg font-semibold">{t('chatPage.landingScreen.tryAsking')}</h3>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={refreshPrompts}
                  className="gap-2"
                >
                  <RefreshCw className="h-4 w-4" />
                  {t('chatPage.landingScreen.refreshPrompts')}
                </Button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl w-full">
                {randomPrompts.map((prompt, index) => (
                  <button
                    key={index}
                    onClick={() => handlePromptClick(prompt)}
                    className="p-4 text-left border rounded-lg hover:bg-accent hover:text-accent-foreground transition-colors duration-200 group"
                  >
                    <div className="flex items-start gap-3">
                      <MessageSquare className="h-5 w-5 text-primary mt-0.5 group-hover:text-accent-foreground transition-colors" />
                      <p className="text-sm leading-relaxed">{prompt}</p>
                    </div>
                  </button>
                ))}
              </div>

              <div className="mt-8 text-center">
                <p className="text-sm text-muted-foreground">
                  {t('chatPage.landingScreen.orTypeQuestion')}
                </p>
              </div>
            </div>
          ) : null}

          {/* Chat Component */}
          <div className="flex-1 min-h-0 pb-4">
            <ElysiaChat
              ref={elysiaChatRef}
              tenantId={tenantId}
              className="h-full"
              initialMessage={t('chatPage.initialMessage')}
              initialQuery={initialQuery || undefined}
              documentId={documentContext?.id}
              onFirstQuery={() => setHasStartedChat(true)}
              isAdmin={backendUser ? (
                backendUser.is_superuser ||
                backendUser.roles?.some((role: any) => role.name === 'admin') ||
                !backendUser.is_team_member
              ) : false}
            />
          </div>
        </div>
      ) : mode === "settings" ? (
        <div className="flex flex-col w-full max-w-4xl mx-auto p-6 flex-1 overflow-y-auto">
          <h2 className="text-2xl font-bold mb-6">{t('chatPage.settingsPage.title')}</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Model Settings */}
            <div className="p-6 border rounded-lg">
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <Brain className="h-5 w-5" />
                {t('chatPage.settingsPage.modelSettings.title')}
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium">{t('chatPage.settingsPage.modelSettings.temperature')}</label>
                  <p className="text-sm text-muted-foreground">{t('chatPage.settingsPage.modelSettings.temperatureDescription')}</p>
                  <Badge variant="secondary">0.7 (por defecto)</Badge>
                </div>
                <div>
                  <label className="text-sm font-medium">{t('chatPage.settingsPage.modelSettings.maxTokens')}</label>
                  <p className="text-sm text-muted-foreground">{t('chatPage.settingsPage.modelSettings.maxTokensDescription')}</p>
                  <Badge variant="secondary">2048</Badge>
                </div>
              </div>
            </div>

            {/* Search Settings */}
            <div className="p-6 border rounded-lg">
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <MessageSquare className="h-5 w-5" />
                {t('chatPage.settingsPage.searchSettings.title')}
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium">{t('chatPage.settingsPage.searchSettings.documentLimit')}</label>
                  <p className="text-sm text-muted-foreground">{t('chatPage.settingsPage.searchSettings.documentLimitDescription')}</p>
                  <Badge variant="secondary">10</Badge>
                </div>
                <div>
                  <label className="text-sm font-medium">{t('chatPage.settingsPage.searchSettings.similarityThreshold')}</label>
                  <p className="text-sm text-muted-foreground">{t('chatPage.settingsPage.searchSettings.similarityThresholdDescription')}</p>
                  <Badge variant="secondary">0.7</Badge>
                </div>
              </div>
            </div>

            {/* User Info */}
            <div className="p-6 border rounded-lg">
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <Settings className="h-5 w-5" />
                {t('chatPage.settingsPage.userInfo.title')}
              </h3>
              <div className="space-y-2">
                <p className="text-sm"><strong>{t('chatPage.settingsPage.userInfo.tenant')}</strong> {tenantId}</p>
                <p className="text-sm"><strong>{t('chatPage.settingsPage.userInfo.user')}</strong> {backendUser?.email || t('chatPage.settingsPage.userInfo.notAvailable')}</p>
                <p className="text-sm"><strong>{t('chatPage.settingsPage.userInfo.role')}</strong> {backendUser?.is_team_member ? t('chatPage.settingsPage.userInfo.member') : t('chatPage.settingsPage.userInfo.admin')}</p>
              </div>
            </div>

            {/* Capabilities */}
            <div className="p-6 border rounded-lg">
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <Zap className="h-5 w-5" />
                {t('chatPage.settingsPage.capabilities.title')}
              </h3>
              <div className="space-y-2">
                <Badge variant="outline">{t('chatPage.settingsPage.capabilities.ragAgentic')}</Badge>
                <Badge variant="outline">{t('chatPage.settingsPage.capabilities.semanticSearch')}</Badge>
                <Badge variant="outline">{t('chatPage.settingsPage.capabilities.documentAnalysis')}</Badge>
                <Badge variant="outline">{t('chatPage.settingsPage.capabilities.contextualResponses')}</Badge>
              </div>
            </div>
          </div>

          <div className="mt-6">
            <Button onClick={() => setMode("chat")} className="gap-2">
              <MessageSquare className="h-4 w-4" />
              {t('chatPage.settingsPage.backToChat')}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}