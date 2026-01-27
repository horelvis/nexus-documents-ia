"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "../ui/button"
import { RadioGroup, RadioGroupItem } from "../ui/radio-group"
import { Checkbox } from "../ui/checkbox"
import { Label } from "../ui/label"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "../ui/card"
import { AlertCircle, HelpCircle, CheckCircle2, Lightbulb } from "lucide-react"

/**
 * Option for clarification UI
 */
export interface ClarificationOption {
  label: string
  value: string
  description?: string
}

/**
 * Props for EmmaClarificationUI
 */
export interface EmmaClarificationUIProps {
  /** The question to display */
  question: string
  /** Short header/category for the question */
  header?: string
  /** Available options */
  options: ClarificationOption[]
  /** Allow multiple selections */
  multiSelect?: boolean
  /** Severity level for confirmation requests */
  severity?: "info" | "warning" | "critical"
  /** Type of request */
  type?: "clarification" | "confirmation" | "suggestion"
  /** Loading state while sending response */
  isLoading?: boolean
  /** Callback when user submits their selection */
  onSubmit: (selectedValues: string[]) => void
  /** Callback when user cancels/dismisses */
  onCancel?: () => void
  /** Additional CSS classes */
  className?: string
}

/**
 * EmmaClarificationUI - Human-in-the-Loop UI for Emma
 *
 * Displays options to the user when Emma needs clarification.
 * Similar to Claude Code's AskUserQuestion UI.
 */
export function EmmaClarificationUI({
  question,
  header = "Opción",
  options,
  multiSelect = false,
  severity = "info",
  type = "clarification",
  isLoading = false,
  onSubmit,
  onCancel,
  className,
}: EmmaClarificationUIProps) {
  const [selectedValues, setSelectedValues] = useState<string[]>([])
  const [customInput, setCustomInput] = useState("")

  // Icon based on type/severity
  const Icon = type === "confirmation"
    ? (severity === "critical" ? AlertCircle : severity === "warning" ? AlertCircle : HelpCircle)
    : type === "suggestion"
    ? Lightbulb
    : HelpCircle

  // Color based on severity
  const severityColors = {
    info: "text-blue-500",
    warning: "text-amber-500",
    critical: "text-red-500",
  }

  // Handle single select
  const handleSingleSelect = (value: string) => {
    setSelectedValues([value])
  }

  // Handle multi select
  const handleMultiSelect = (value: string, checked: boolean) => {
    if (checked) {
      setSelectedValues([...selectedValues, value])
    } else {
      setSelectedValues(selectedValues.filter(v => v !== value))
    }
  }

  // Handle submit
  const handleSubmit = () => {
    if (selectedValues.length === 0 && !customInput) return

    // If custom input provided, use that
    if (customInput) {
      onSubmit([`custom:${customInput}`])
    } else {
      onSubmit(selectedValues)
    }
  }

  // Check if submit is enabled
  const canSubmit = selectedValues.length > 0 || customInput.trim().length > 0

  return (
    <Card className={cn(
      "w-full max-w-md mx-auto border-2 animate-in fade-in-50 slide-in-from-bottom-5 duration-300",
      severity === "critical" && "border-red-200 bg-red-50/50",
      severity === "warning" && "border-amber-200 bg-amber-50/50",
      severity === "info" && "border-blue-200 bg-blue-50/50",
      className
    )}>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Icon className={cn("h-5 w-5", severityColors[severity])} />
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {header}
          </span>
        </div>
        <CardTitle className="text-base font-medium leading-relaxed">
          {question}
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-3">
        {multiSelect ? (
          // Multi-select with checkboxes
          <div className="space-y-2">
            {options.map((option) => (
              <div
                key={option.value}
                className={cn(
                  "flex items-start space-x-3 p-3 rounded-lg border transition-colors cursor-pointer",
                  selectedValues.includes(option.value)
                    ? "bg-primary/5 border-primary"
                    : "hover:bg-muted/50 border-transparent"
                )}
                onClick={() => handleMultiSelect(option.value, !selectedValues.includes(option.value))}
              >
                <Checkbox
                  id={option.value}
                  checked={selectedValues.includes(option.value)}
                  onCheckedChange={(checked) => handleMultiSelect(option.value, checked as boolean)}
                />
                <div className="flex flex-col">
                  <Label htmlFor={option.value} className="font-medium cursor-pointer">
                    {option.label}
                  </Label>
                  {option.description && (
                    <span className="text-sm text-muted-foreground mt-0.5">
                      {option.description}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          // Single select with radio buttons
          <RadioGroup
            value={selectedValues[0] || ""}
            onValueChange={handleSingleSelect}
            className="space-y-2"
          >
            {options.map((option) => (
              <div
                key={option.value}
                className={cn(
                  "flex items-start space-x-3 p-3 rounded-lg border transition-colors cursor-pointer",
                  selectedValues[0] === option.value
                    ? "bg-primary/5 border-primary"
                    : "hover:bg-muted/50 border-transparent"
                )}
                onClick={() => handleSingleSelect(option.value)}
              >
                <RadioGroupItem value={option.value} id={option.value} />
                <div className="flex flex-col">
                  <Label htmlFor={option.value} className="font-medium cursor-pointer">
                    {option.label}
                  </Label>
                  {option.description && (
                    <span className="text-sm text-muted-foreground mt-0.5">
                      {option.description}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </RadioGroup>
        )}

        {/* Custom input option (always available as "Other") */}
        <div className="pt-2 border-t">
          <Label htmlFor="custom-input" className="text-sm text-muted-foreground">
            O escribe tu propia respuesta:
          </Label>
          <input
            id="custom-input"
            type="text"
            value={customInput}
            onChange={(e) => {
              setCustomInput(e.target.value)
              if (e.target.value) setSelectedValues([]) // Clear selections if typing
            }}
            placeholder="Escribe aquí..."
            className="w-full mt-1.5 px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>
      </CardContent>

      <CardFooter className="flex gap-2">
        {onCancel && (
          <Button
            variant="outline"
            onClick={onCancel}
            disabled={isLoading}
            className="flex-1"
          >
            Cancelar
          </Button>
        )}
        <Button
          onClick={handleSubmit}
          disabled={!canSubmit || isLoading}
          className={cn(
            "flex-1",
            severity === "critical" && "bg-red-600 hover:bg-red-700",
            severity === "warning" && "bg-amber-600 hover:bg-amber-700"
          )}
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
              Enviando...
            </span>
          ) : type === "confirmation" ? (
            <span className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              Confirmar
            </span>
          ) : (
            "Continuar"
          )}
        </Button>
      </CardFooter>
    </Card>
  )
}

export default EmmaClarificationUI
