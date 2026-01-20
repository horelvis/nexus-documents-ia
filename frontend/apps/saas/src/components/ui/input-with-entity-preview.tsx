"use client"

import { InputWithMentions, TextareaWithMentions } from "./input-with-mentions"

interface InputWithEntityPreviewProps {
  value: string
  onChange: (value: string) => void
  documentId?: string
  placeholder?: string
  onEntitySelect?: (entity: any) => void
  mentionTrigger?: string
  className?: string
  disabled?: boolean
  variant?: 'input' | 'textarea'
  rows?: number
  onKeyDown?: (e: React.KeyboardEvent) => void
}

export function InputWithEntityPreview({
  value,
  onChange,
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
    </div>
  )
}
