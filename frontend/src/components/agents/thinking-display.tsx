'use client'

import React from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Brain, Lightbulb, Target, Eye, CheckCircle2, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ThinkingEvent {
  type: 'thinking' | 'reasoning' | 'planning' | 'observation' | 'conclusion'
  content: string
  metadata?: {
    timestamp?: string
    step?: number
    steps?: string[]
    evidence?: string[]
    confidence?: number
    phase?: string
    [key: string]: any
  }
}

interface ThinkingDisplayProps {
  events: ThinkingEvent[]
  isStreaming?: boolean
  className?: string
}

const eventIcons = {
  thinking: Brain,
  reasoning: Lightbulb,
  planning: Target,
  observation: Eye,
  conclusion: CheckCircle2
}

const eventColors = {
  thinking: 'text-blue-600 bg-blue-50 border-blue-200',
  reasoning: 'text-purple-600 bg-purple-50 border-purple-200',
  planning: 'text-green-600 bg-green-50 border-green-200',
  observation: 'text-orange-600 bg-orange-50 border-orange-200',
  conclusion: 'text-emerald-600 bg-emerald-50 border-emerald-200'
}

export function ThinkingDisplay({ events, isStreaming = false, className }: ThinkingDisplayProps) {
  const latestEvent = events[events.length - 1]

  return (
    <div className={cn("space-y-3", className)}>
      <AnimatePresence mode="popLayout">
        {events.map((event, index) => {
          const Icon = eventIcons[event.type] || AlertCircle
          const colorClass = eventColors[event.type] || 'text-gray-600 bg-gray-50 border-gray-200'
          const isLatest = index === events.length - 1

          return (
            <motion.div
              key={`${event.type}-${index}`}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
              className={cn(
                "relative rounded-lg border p-4 transition-all",
                colorClass,
                isLatest && isStreaming && "ring-2 ring-offset-2 ring-blue-400"
              )}
            >
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0">
                  <Icon className="h-5 w-5 mt-0.5" />
                </div>
                <div className="flex-1 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium capitalize">
                      {event.type}
                      {event.metadata?.step && ` - Step ${event.metadata.step}`}
                    </span>
                    {event.metadata?.phase && (
                      <span className="text-xs opacity-75">
                        {event.metadata.phase}
                      </span>
                    )}
                  </div>
                  
                  <p className="text-sm leading-relaxed">{event.content}</p>
                  
                  {/* Planning steps */}
                  {event.type === 'planning' && event.metadata?.steps && (
                    <ul className="mt-3 space-y-1 text-xs">
                      {event.metadata.steps.map((step, i) => (
                        <li key={i} className="flex items-center gap-2">
                          <span className="flex-shrink-0 w-5 h-5 rounded-full bg-white/50 flex items-center justify-center text-xs font-medium">
                            {i + 1}
                          </span>
                          <span>{step}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  
                  {/* Evidence for reasoning */}
                  {event.type === 'reasoning' && event.metadata?.evidence && event.metadata.evidence.length > 0 && (
                    <div className="mt-3 text-xs space-y-1">
                      <span className="font-medium">Evidence:</span>
                      {event.metadata.evidence.map((evidence, i) => (
                        <div key={i} className="pl-4 opacity-75">• {evidence}</div>
                      ))}
                    </div>
                  )}
                  
                  {/* Confidence for conclusions */}
                  {event.type === 'conclusion' && event.metadata?.confidence !== undefined && (
                    <div className="mt-3 flex items-center gap-2">
                      <span className="text-xs font-medium">Confidence:</span>
                      <div className="flex-1 h-2 bg-white/30 rounded-full overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${event.metadata.confidence * 100}%` }}
                          transition={{ duration: 0.5, ease: 'easeOut' }}
                          className="h-full bg-current rounded-full"
                        />
                      </div>
                      <span className="text-xs">{Math.round(event.metadata.confidence * 100)}%</span>
                    </div>
                  )}
                  
                  {/* Additional metadata */}
                  {event.metadata?.data && (
                    <div className="mt-2 text-xs opacity-75">
                      <details className="cursor-pointer">
                        <summary className="hover:underline">Additional data</summary>
                        <pre className="mt-2 p-2 bg-white/30 rounded overflow-x-auto">
                          {JSON.stringify(event.metadata.data, null, 2)}
                        </pre>
                      </details>
                    </div>
                  )}
                </div>
              </div>
              
              {/* Streaming indicator */}
              {isLatest && isStreaming && (
                <motion.div
                  className="absolute -bottom-1 left-1/2 transform -translate-x-1/2"
                  animate={{ opacity: [0.5, 1, 0.5] }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                >
                  <div className="w-2 h-2 rounded-full bg-current" />
                </motion.div>
              )}
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}