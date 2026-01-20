"use client"

import { ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { IconUser, IconBuilding, IconRobot } from "@tabler/icons-react"

export interface EntityTag {
  type: string
  id: string
  name: string
}

interface EntityRendererProps {
  text: string
  className?: string
}

// Parse entity tags from text like: <@user:123:Juan Pérez>
export function parseEntityTags(text: string): Array<{
  type: 'text' | 'entity',
  content: string,
  entity?: EntityTag,
  start: number,
  end: number
}> {
  const parts: Array<{
    type: 'text' | 'entity',
    content: string,
    entity?: EntityTag,
    start: number,
    end: number
  }> = []

  const legacyRegex = /<@([^:>]+):([^:>]+):([^>]+)>/g
  const matches: Array<{
    start: number
    end: number
    content: string
    entity?: EntityTag
  }> = []

  let match: RegExpExecArray | null

  while ((match = legacyRegex.exec(text)) !== null) {
    matches.push({
      start: match.index,
      end: match.index + match[0].length,
      content: match[0],
      entity: {
        type: match[1],
        id: match[2],
        name: match[3]
      }
    })
  }

  matches.sort((a, b) => a.start - b.start)

  let cursor = 0
  for (const entry of matches) {
    if (entry.start > cursor) {
      parts.push({
        type: 'text',
        content: text.substring(cursor, entry.start),
        start: cursor,
        end: entry.start
      })
    }

    parts.push({
      type: 'entity',
      content: entry.content,
      entity: entry.entity,
      start: entry.start,
      end: entry.end
    })

    cursor = entry.end
  }

  if (cursor < text.length) {
    parts.push({
      type: 'text',
      content: text.substring(cursor),
      start: cursor,
      end: text.length
    })
  }

  return parts
}

// Component to render text with entity tags as badges
export function EntityRenderer({ text, className }: EntityRendererProps) {
  const parts = parseEntityTags(text)

  return (
    <div className={className}>
      {parts.map((part, index) => {
        if (part.type === 'text') {
          return <span key={index}>{part.content}</span>
        }

        if (part.type === 'entity' && part.entity) {
          const { type, name } = part.entity
          const Icon = type === 'organization' ? IconBuilding : 
                      type === 'agent' ? IconRobot : IconUser

          return (
            <Badge 
              key={index} 
              variant="secondary" 
              className="inline-flex items-center gap-1 mx-1 bg-primary/10 text-primary hover:bg-primary/20 border-primary/20"
            >
              <Icon className="h-3 w-3" />
              {name}
            </Badge>
          )
        }

        return null
      })}
    </div>
  )
}

// Helper function to create entity tag
export function createEntityTag(entity: EntityTag): string {
  return `<@${entity.type}:${entity.id}:${entity.name}>`
}

// Helper function to extract plain text from text with entity tags
export function extractPlainText(text: string): string {
  return text.replace(/<@[^:]+:[^:]+:([^>]+)>/g, '@$1')
}

// Helper function to check if cursor is inside an entity tag
export function findEntityAtPosition(text: string, position: number): {
  entity: EntityTag,
  start: number,
  end: number
} | null {
  const parts = parseEntityTags(text)
  
  for (const part of parts) {
    if (part.type === 'entity' && position >= part.start && position <= part.end && part.entity) {
      return {
        entity: part.entity,
        start: part.start,
        end: part.end
      }
    }
  }
  
  return null
}
