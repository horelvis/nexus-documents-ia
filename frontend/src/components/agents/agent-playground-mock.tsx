'use client'

/**
 * AgentPlaygroundMock — simulated SSE playground for the agent builder.
 *
 * Renders a chat-like preview that streams a fake trace (thinking, tool calls,
 * synthesis) based on the draft config. Zero network calls.
 */

import { useEffect, useRef, useState } from 'react'
import { Button, Input, Badge, Card, CardContent, CardHeader, CardTitle, ScrollArea, Separator } from '@/components/ui'
import { IconSend, IconPlayerStop, IconRefresh, IconBolt, IconTool, IconCheck } from '@tabler/icons-react'
import { mockStreamResponse, type DraftConfig, type MockSSEEvent } from '@/lib/mocks/agents-mock'

type TraceItem =
  | { kind: 'user'; text: string }
  | { kind: 'thinking'; text: string }
  | { kind: 'tool'; tool: string; latency_ms?: number; done: boolean }
  | { kind: 'assistant'; text: string }

interface AgentPlaygroundMockProps {
  draftConfig: DraftConfig
  disabled?: boolean
  agentIcon?: string
  agentName?: string
}

export function AgentPlaygroundMock({
  draftConfig,
  disabled,
  agentIcon = '🤖',
  agentName = 'Agente (borrador)',
}: AgentPlaygroundMockProps) {
  const [input, setInput] = useState('')
  const [trace, setTrace] = useState<TraceItem[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [trace])

  const canSend = !disabled && !isStreaming && input.trim().length > 0

  const handleSend = async () => {
    const query = input.trim()
    if (!query) return

    setInput('')
    setTrace((prev) => [...prev, { kind: 'user', text: query }])
    setIsStreaming(true)

    const controller = new AbortController()
    abortRef.current = controller

    let assistantBuffer = ''
    let assistantIdx = -1

    try {
      for await (const evt of mockStreamResponse(query, draftConfig, controller.signal)) {
        setTrace((prev) => applyEvent(prev, evt, { assistantIdx, assistantBuffer }))
        if (evt.type === 'token' && evt.content) {
          assistantBuffer += evt.content
          if (assistantIdx === -1) assistantIdx = -2 // will be set on first setTrace below
        }
      }
    } catch (err) {
      if ((err as { name?: string })?.name !== 'AbortError') {
        setTrace((prev) => [...prev, { kind: 'assistant', text: '(error en el playground simulado)' }])
      }
    } finally {
      setIsStreaming(false)
      abortRef.current = null
    }
  }

  const handleStop = () => {
    abortRef.current?.abort()
  }

  const handleClear = () => {
    setTrace([])
  }

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="flex flex-row items-center justify-between py-3 border-b shrink-0">
        <CardTitle className="text-sm flex items-center gap-2">
          <IconBolt className="h-4 w-4 text-amber-500" />
          Playground <span className="text-muted-foreground font-normal">(simulado)</span>
        </CardTitle>
        <Button variant="ghost" size="sm" onClick={handleClear} disabled={trace.length === 0}>
          <IconRefresh className="h-4 w-4 mr-1" /> Limpiar
        </Button>
      </CardHeader>

      <CardContent className="flex-1 flex flex-col p-0 min-h-0">
        <ScrollArea className="flex-1 p-4" ref={scrollRef as never}>
          {trace.length === 0 && (
            <div className="text-center text-sm text-muted-foreground py-12 space-y-2">
              <div className="text-4xl">{agentIcon}</div>
              <p className="font-medium">{agentName}</p>
              <p className="text-xs max-w-xs mx-auto">
                Escribe un mensaje de prueba para ver cómo razona el agente con tu configuración actual.
              </p>
              <div className="flex flex-wrap justify-center gap-1 pt-3 max-w-sm mx-auto">
                {draftConfig.allowed_tools.slice(0, 6).map((t) => (
                  <Badge key={t} variant="outline" className="text-[10px]">{t}</Badge>
                ))}
                {draftConfig.allowed_tools.length > 6 && (
                  <Badge variant="outline" className="text-[10px]">+{draftConfig.allowed_tools.length - 6}</Badge>
                )}
              </div>
            </div>
          )}

          <div className="space-y-3">
            {trace.map((item, i) => (
              <TraceRow key={i} item={item} agentIcon={agentIcon} />
            ))}
            {isStreaming && (
              <div className="text-xs text-muted-foreground flex items-center gap-2 animate-pulse">
                <span className="inline-block h-2 w-2 rounded-full bg-amber-500" /> procesando…
              </div>
            )}
          </div>
        </ScrollArea>

        <Separator />

        <div className="p-3 flex gap-2 shrink-0">
          <Input
            placeholder={disabled ? 'Completa la configuración primero' : 'Mensaje de prueba…'}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && canSend) handleSend()
            }}
            disabled={disabled || isStreaming}
          />
          {isStreaming ? (
            <Button variant="destructive" size="icon" onClick={handleStop}>
              <IconPlayerStop className="h-4 w-4" />
            </Button>
          ) : (
            <Button size="icon" onClick={handleSend} disabled={!canSend}>
              <IconSend className="h-4 w-4" />
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function applyEvent(
  prev: TraceItem[],
  evt: MockSSEEvent,
  _ctx: { assistantIdx: number; assistantBuffer: string },
): TraceItem[] {
  switch (evt.type) {
    case 'thinking':
      return [...prev, { kind: 'thinking', text: evt.content ?? '' }]
    case 'tool_call':
      return [...prev, { kind: 'tool', tool: evt.tool ?? 'unknown', done: false }]
    case 'tool_result': {
      const next = [...prev]
      for (let i = next.length - 1; i >= 0; i--) {
        const row = next[i]
        if (row.kind === 'tool' && row.tool === evt.tool && !row.done) {
          next[i] = { ...row, done: true, latency_ms: evt.latency_ms }
          break
        }
      }
      return next
    }
    case 'token': {
      const next = [...prev]
      const last = next[next.length - 1]
      if (last && last.kind === 'assistant') {
        next[next.length - 1] = { kind: 'assistant', text: last.text + (evt.content ?? '') }
      } else {
        next.push({ kind: 'assistant', text: evt.content ?? '' })
      }
      return next
    }
    case 'done':
      return prev
    default:
      return prev
  }
}

function TraceRow({ item, agentIcon }: { item: TraceItem; agentIcon: string }) {
  if (item.kind === 'user') {
    return (
      <div className="flex justify-end">
        <div className="bg-primary text-primary-foreground rounded-lg px-3 py-2 text-sm max-w-[80%]">
          {item.text}
        </div>
      </div>
    )
  }
  if (item.kind === 'thinking') {
    return (
      <div className="text-xs text-muted-foreground italic pl-8">
        ▸ {item.text}
      </div>
    )
  }
  if (item.kind === 'tool') {
    return (
      <div className="flex items-center gap-2 pl-8 text-xs">
        {item.done ? (
          <IconCheck className="h-3.5 w-3.5 text-emerald-500" />
        ) : (
          <IconTool className="h-3.5 w-3.5 text-amber-500 animate-pulse" />
        )}
        <Badge variant="outline" className="font-mono text-[10px]">{item.tool}</Badge>
        {item.done && item.latency_ms != null && (
          <span className="text-muted-foreground">{item.latency_ms}ms</span>
        )}
      </div>
    )
  }
  return (
    <div className="flex gap-2 items-start">
      <div className="text-lg leading-none pt-0.5">{agentIcon}</div>
      <div className="flex-1 text-sm whitespace-pre-wrap">{item.text}</div>
    </div>
  )
}
