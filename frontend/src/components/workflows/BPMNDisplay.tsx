"use client"

import { Card, CardContent } from "@/components/ui/card"

interface BPMNDisplayProps {
  initialBpmn: string
  height?: string
}

export function BPMNDisplay({ initialBpmn, height = "400px" }: BPMNDisplayProps) {
  if (!initialBpmn) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No BPMN XML content to display
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardContent className="p-4">
        <div
          className="bg-gray-900 rounded-lg p-4 overflow-auto"
          style={{ height }}
        >
          <pre className="text-sm text-green-400 font-mono whitespace-pre-wrap">
            {initialBpmn}
          </pre>
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          Full BPMN editor will be available in a future update.
          Use Camunda Modeler for advanced editing.
        </p>
      </CardContent>
    </Card>
  )
}
