"use client"

import { ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { IconUser, IconBuilding, IconRobot } from "@tabler/icons-react"

interface EntityTag {
  type: 'user' | 'contact' | 'organization' | 'agent'
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
  
  const entityRegex = /<@(user|contact|organization|agent):([^:]+):([^>]+)>/g
  let lastIndex = 0
  let match

  while ((match = entityRegex.exec(text)) !== null) {
    // Add text before the entity
    if (match.index > lastIndex) {
      parts.push({
        type: 'text',
        content: text.substring(lastIndex, match.index),
        start: lastIndex,
        end: match.index
      })
    }

    // Add the entity
    parts.push({
      type: 'entity',
      content: match[0],
      entity: {
        type: match[1] as EntityTag['type'],
        id: match[2],
        name: match[3]
      },
      start: match.index,
      end: match.index + match[0].length
    })

    lastIndex = match.index + match[0].length
  }

  // Add remaining text
  if (lastIndex < text.length) {
    parts.push({
      type: 'text',
      content: text.substring(lastIndex),
      start: lastIndex,
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