"use client"

import { Card, CardContent } from "@/components/ui/card"

interface BPMNVisualizerProps {
  bpmnText: string
}

export function BPMNVisualizer({ bpmnText }: BPMNVisualizerProps) {
  if (!bpmnText) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No BPMN content to display
        </CardContent>
      </Card>
    )
  }

  // Simple text-based visualization
  const lines = bpmnText.split('\n').filter(line => line.trim())

  return (
    <Card>
      <CardContent className="p-4">
        <div className="bg-gray-50 rounded-lg p-4 overflow-auto max-h-[400px]">
          <pre className="text-sm whitespace-pre-wrap font-mono">
            {lines.map((line, idx) => (
              <div key={idx} className="py-0.5">
                {line}
              </div>
            ))}
          </pre>
        </div>
      </CardContent>
    </Card>
  )
}
