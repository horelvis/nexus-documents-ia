"use client"

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Download, Code2 } from 'lucide-react'
import { useState } from 'react'

interface BPMNDisplayProps {
  initialBpmn?: string
  onSave?: (bpmnXml: string) => void
  readonly?: boolean
  height?: string
}

export function BPMNDisplay({ 
  initialBpmn = "", 
  readonly = false, 
  height = "500px" 
}: BPMNDisplayProps) {
  const [showCode, setShowCode] = useState(false)

  const handleDownload = () => {
    if (initialBpmn) {
      const blob = new Blob([initialBpmn], { type: 'application/xml' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'diagram.bpmn'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Code2 className="h-5 w-5" />
            BPMN Display
            <Badge variant="secondary">Simple</Badge>
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowCode(!showCode)}
            >
              {showCode ? 'Vista Resumida' : 'Ver Código'}
            </Button>
            
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownload}
              disabled={!initialBpmn}
            >
              <Download className="h-4 w-4 mr-2" />
              Descargar
            </Button>
          </div>
        </div>
      </CardHeader>
      
      <CardContent>
        {showCode ? (
          <div className="bg-gray-50 p-4 rounded-lg">
            <h4 className="font-semibold mb-2">XML BPMN</h4>
            <pre className="bg-black text-green-400 p-4 rounded text-xs overflow-auto max-h-96">
              <code>{initialBpmn || 'No hay contenido BPMN'}</code>
            </pre>
          </div>
        ) : (
          <div 
            style={{ height, minHeight: '400px' }}
            className="border border-gray-200 rounded-md bg-gradient-to-br from-blue-50 to-indigo-50 flex items-center justify-center"
          >
            <div className="text-center p-8">
              <div className="text-6xl mb-4">📊</div>
              <h3 className="text-lg font-semibold text-gray-700 mb-2">
                Diagrama BPMN Generado
              </h3>
              <p className="text-gray-600 mb-4">
                El diagrama ha sido generado exitosamente
              </p>
              <div className="space-y-2 text-sm text-gray-500">
                <p>• Usa el botón "Ver Código" para ver el XML</p>
                <p>• Usa "Descargar" para guardar el archivo .bpmn</p>
                <p>• El diagrama puede importarse en cualquier editor BPMN</p>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}