"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Send, Pencil, X, RotateCcw, Shield } from "lucide-react"
import type { HITLReviewRequest, HITLDecision } from "@/lib/types/emma"

/**
 * Convert snake_case key to Title Case for display.
 */
function prettifyKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export interface HITLReviewCardProps {
  request: HITLReviewRequest
  isLoading?: boolean
  onSubmit: (decision: HITLDecision) => void
}

/**
 * HITLReviewCard — Human-in-the-Loop review card for action approval.
 *
 * Three modes:
 *  - view: read-only display of proposed action args + decision buttons
 *  - edit: editable fields for modifying args before approval
 *  - reject: feedback textarea for rejection reason
 */
export function HITLReviewCard({
  request,
  isLoading = false,
  onSubmit,
}: HITLReviewCardProps) {
  const [mode, setMode] = useState<"view" | "edit" | "reject">("view")
  const [editedArgs, setEditedArgs] = useState<Record<string, unknown>>(
    () => ({ ...request.action_request.args })
  )
  const [rejectMessage, setRejectMessage] = useState("")

  const { action_request, review_config } = request
  const canApprove = review_config.allowed_decisions.includes("approve")
  const canEdit = review_config.allowed_decisions.includes("edit")
  const canReject = review_config.allowed_decisions.includes("reject")

  const handleApprove = () => {
    onSubmit({ type: "approve" })
  }

  const handleEditSubmit = () => {
    onSubmit({ type: "edit", edited_args: editedArgs })
  }

  const handleRejectSubmit = () => {
    onSubmit({ type: "reject", message: rejectMessage || undefined })
  }

  const handleReset = () => {
    setEditedArgs({ ...action_request.args })
  }

  const handleCancel = () => {
    setMode("view")
    setRejectMessage("")
    setEditedArgs({ ...action_request.args })
  }

  const handleEditField = (key: string, value: string) => {
    setEditedArgs((prev) => ({ ...prev, [key]: value }))
  }

  // Determine which fields are editable (all if not specified)
  const editableFields = review_config.editable_fields ?? Object.keys(action_request.args)

  return (
    <Card className={cn(
      "w-full max-w-lg mx-auto border-2 animate-in fade-in-50 slide-in-from-bottom-5 duration-300",
      mode === "view" && "border-blue-200 bg-blue-50/50 dark:border-blue-800 dark:bg-blue-950/30",
      mode === "edit" && "border-amber-200 bg-amber-50/50 dark:border-amber-800 dark:bg-amber-950/30",
      mode === "reject" && "border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-950/30",
    )}>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-blue-500 dark:text-blue-400" />
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Requiere aprobacion
          </span>
        </div>
        <CardTitle className="text-base font-medium leading-relaxed">
          {action_request.description || `Accion: ${action_request.name}`}
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Action name badge */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono px-2 py-1 rounded bg-muted dark:bg-muted/50 text-muted-foreground">
            {action_request.name}
          </span>
        </div>

        {/* Args display / edit */}
        <div className="space-y-3">
          {Object.entries(mode === "edit" ? editedArgs : action_request.args).map(
            ([key, value]) => {
              const isEditable = mode === "edit" && editableFields.includes(key)

              return (
                <div key={key} className="space-y-1">
                  <label className="text-sm font-medium text-muted-foreground">
                    {prettifyKey(key)}
                  </label>
                  {isEditable ? (
                    <Textarea
                      value={String(value ?? "")}
                      onChange={(e) => handleEditField(key, e.target.value)}
                      className="text-sm border-amber-300 dark:border-amber-700 focus:ring-amber-400"
                      rows={2}
                    />
                  ) : (
                    <div className="text-sm px-3 py-2 rounded-md bg-muted/50 dark:bg-muted/30 whitespace-pre-wrap break-words">
                      {typeof value === "object" ? JSON.stringify(value, null, 2) : String(value ?? "")}
                    </div>
                  )}
                </div>
              )
            }
          )}
        </div>

        {/* Reject mode: feedback textarea */}
        {mode === "reject" && (
          <div className="space-y-1 pt-2 border-t border-red-200 dark:border-red-800">
            <label className="text-sm font-medium text-muted-foreground">
              Motivo del rechazo (opcional)
            </label>
            <Textarea
              value={rejectMessage}
              onChange={(e) => setRejectMessage(e.target.value)}
              placeholder="Explica por que rechazas esta accion..."
              className="text-sm border-red-300 dark:border-red-700 focus:ring-red-400"
              rows={3}
            />
          </div>
        )}

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2 pt-2">
          {mode === "view" && (
            <>
              {canApprove && (
                <Button
                  onClick={handleApprove}
                  disabled={isLoading}
                  size="sm"
                  className="bg-green-600 hover:bg-green-700 dark:bg-green-700 dark:hover:bg-green-600"
                >
                  {isLoading ? (
                    <span className="flex items-center gap-2">
                      <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
                      Enviando...
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Send className="h-4 w-4" />
                      Aprobar
                    </span>
                  )}
                </Button>
              )}
              {canEdit && (
                <Button
                  onClick={() => setMode("edit")}
                  disabled={isLoading}
                  variant="outline"
                  size="sm"
                  className="border-amber-300 text-amber-700 hover:bg-amber-50 dark:border-amber-700 dark:text-amber-400 dark:hover:bg-amber-950/50"
                >
                  <span className="flex items-center gap-2">
                    <Pencil className="h-4 w-4" />
                    Editar
                  </span>
                </Button>
              )}
              {canReject && (
                <Button
                  onClick={() => setMode("reject")}
                  disabled={isLoading}
                  variant="outline"
                  size="sm"
                  className="border-red-300 text-red-700 hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-950/50"
                >
                  <span className="flex items-center gap-2">
                    <X className="h-4 w-4" />
                    Rechazar
                  </span>
                </Button>
              )}
            </>
          )}

          {mode === "edit" && (
            <>
              <Button
                onClick={handleEditSubmit}
                disabled={isLoading}
                size="sm"
                className="bg-amber-600 hover:bg-amber-700 dark:bg-amber-700 dark:hover:bg-amber-600"
              >
                {isLoading ? (
                  <span className="flex items-center gap-2">
                    <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
                    Enviando...
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <Send className="h-4 w-4" />
                    Enviar editado
                  </span>
                )}
              </Button>
              <Button
                onClick={handleReset}
                disabled={isLoading}
                variant="outline"
                size="sm"
              >
                <span className="flex items-center gap-2">
                  <RotateCcw className="h-4 w-4" />
                  Restablecer
                </span>
              </Button>
              <Button
                onClick={handleCancel}
                disabled={isLoading}
                variant="ghost"
                size="sm"
              >
                Cancelar
              </Button>
            </>
          )}

          {mode === "reject" && (
            <>
              <Button
                onClick={handleRejectSubmit}
                disabled={isLoading}
                size="sm"
                className="bg-red-600 hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600"
              >
                {isLoading ? (
                  <span className="flex items-center gap-2">
                    <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
                    Enviando...
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <X className="h-4 w-4" />
                    Confirmar rechazo
                  </span>
                )}
              </Button>
              <Button
                onClick={handleCancel}
                disabled={isLoading}
                variant="ghost"
                size="sm"
              >
                Cancelar
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export default HITLReviewCard
