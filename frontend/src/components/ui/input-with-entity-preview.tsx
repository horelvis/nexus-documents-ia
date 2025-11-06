"use client"

import { InputWithMentions, TextareaWithMentions } from "./input-with-mentions"
import { EntityRenderer, extractPlainText } from "./entity-renderer"

interface InputWithEntityPreviewProps {
  value: string
  onChange: (value: string) => void
  documentId?: string
  placeholder?: string
  onEntitySelect?: (entity: any) => void
  mentionTrigger?: string
  className?: string
  disabled?: boolean
  showPreview?: boolean
  variant?: 'input' | 'textarea'
  rows?: number
  onKeyDown?: (e: React.KeyboardEvent) => void
}

export function InputWithEntityPreview({
  value,
  onChange,
  showPreview = true,
  variant = 'input',
  ...props
}: InputWithEntityPreviewProps) {
  return (
    <div className="space-y-2">
      {/* Actual input */}
      {variant === 'textarea' ? (
        <TextareaWithMentions
          value={value}
          onChange={onChange}
          documentId={props.documentId}
          placeholder={props.placeholder}
          onEntitySelect={props.onEntitySelect}
          mentionTrigger={props.mentionTrigger}
          className={props.className}
          disabled={props.disabled}
          rows={props.rows}
          onKeyDown={props.onKeyDown}
        />
      ) : (
        <InputWithMentions
          value={value}
          onChange={onChange}
          documentId={props.documentId}
          placeholder={props.placeholder}
          onEntitySelect={props.onEntitySelect}
          mentionTrigger={props.mentionTrigger}
          className={props.className}
          disabled={props.disabled}
          onKeyDown={props.onKeyDown}
        />
      )}
      
      {/* Preview with rendered entities */}
      {showPreview && value.includes('<@') && (
        <div className="text-sm bg-muted/30 border rounded-md p-2">
          <div className="text-xs text-muted-foreground mb-1">Preview:</div>
          <EntityRenderer text={value} />
        </div>
      )}
    </div>
  )
}