"use client"

import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Download, Upload, Save, Eye, Edit3, AlertCircle } from 'lucide-react'

interface BPMNEditorSimpleProps {
  initialBpmn?: string
  onSave?: (bpmnXml: string) => void
  readonly?: boolean
  height?: string
}

export function BPMNEditorSimple({ 
  initialBpmn, 
  onSave, 
  readonly = false, 
  height = "500px" 
}: BPMNEditorSimpleProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const modelerRef = useRef<any>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [currentBpmn, setCurrentBpmn] = useState<string>("")
  const [isViewMode, setIsViewMode] = useState(readonly)

  useEffect(() => {
    let mounted = true

    const loadAndInitialize = async () => {
      try {
        console.log('🔄 Loading BPMN editor...')
        setIsLoading(true)
        setError(null)

        if (typeof window === 'undefined' || !containerRef.current) {
          console.log('❌ Not in browser or no container')
          return
        }

        console.log('📦 Importing bpmn-js...')
        
        // Simple direct import
        const bpmnJsModule = await import('bpmn-js')
        console.log('✅ BPMN-JS loaded:', bpmnJsModule)
        
        const BpmnModeler = (bpmnJsModule as any).default || bpmnJsModule
        
        if (!mounted) {
          console.log('❌ Component unmounted during load')
          return
        }

        console.log('🏗️ Creating BPMN instance...')
        
        // Clean container first
        if (containerRef.current) {
          containerRef.current.innerHTML = ''
        }

        // Create modeler instance
        modelerRef.current = new BpmnModeler({
          container: containerRef.current,
          width: '100%',
          height: height
        })

        console.log('✅ BPMN instance created')

        // Set up event listeners
        modelerRef.current.on('import.done', () => {
          console.log('✅ BPMN import completed')
          if (mounted) {
            setIsLoading(false)
          }
        })

        modelerRef.current.on('import.error', (event: any) => {
          console.error('❌ BPMN import error:', event.error)
          if (mounted) {
            setError(`Error importing BPMN: ${event.error.message}`)
            setIsLoading(false)
          }
        })

        // Load initial BPMN
        const bpmnToLoad = initialBpmn || getDefaultBpmn()
        console.log('📄 Loading BPMN XML...')
        await modelerRef.current.importXML(bpmnToLoad)
        
        if (mounted) {
          setCurrentBpmn(bpmnToLoad)
          console.log('✅ BPMN editor initialized successfully')
        }

      } catch (err: any) {
        console.error('❌ Error initializing BPMN editor:', err)
        if (mounted) {
          setError(`Failed to load BPMN editor: ${err.message}`)
          setIsLoading(false)
        }
      }
    }

    loadAndInitialize()

    return () => {
      mounted = false
      if (modelerRef.current) {
        try {
          modelerRef.current.destroy()
        } catch (e) {
          console.warn('Error cleaning up BPMN modeler:', e)
        }
        modelerRef.current = null
      }
    }
  }, [initialBpmn, height])

  const getDefaultBpmn = () => {
    return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn2:definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
                   xmlns:bpmn2="http://www.omg.org/spec/BPMN/20100524/MODEL" 
                   xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" 
                   xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" 
                   xsi:schemaLocation="http://www.omg.org/spec/BPMN/20100524/MODEL BPMN20.xsd" 
                   id="Definitions_1" 
                   targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn2:process id="Process_1" isExecutable="false">
    <bpmn2:startEvent id="StartEvent_1"/>
  </bpmn2:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_1">
      <bpmndi:BPMNShape id="_BPMNShape_StartEvent_2" bpmnElement="StartEvent_1">
        <dc:Bounds height="36.0" width="36.0" x="412.0" y="240.0"/>
      </bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn2:definitions>`
  }

  const handleSave = async () => {
    if (!modelerRef.current) return

    try {
      const result = await modelerRef.current.saveXML({ format: true })
      const xml = result.xml
      setCurrentBpmn(xml)
      onSave?.(xml)
    } catch (err: any) {
      console.error('Error saving BPMN:', err)
      setError('Error saving diagram')
    }
  }

  const handleDownload = async () => {
    if (!modelerRef.current) return

    try {
      const result = await modelerRef.current.saveXML({ format: true })
      const xml = result.xml
      const blob = new Blob([xml], { type: 'application/xml' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'diagram.bpmn'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err: any) {
      console.error('Error downloading BPMN:', err)
      setError('Error downloading diagram')
    }
  }

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file || !modelerRef.current) return

    const reader = new FileReader()
    reader.onload = async (e) => {
      try {
        const xml = e.target?.result as string
        await modelerRef.current.importXML(xml)
        setCurrentBpmn(xml)
        setError(null)
      } catch (err: any) {
        console.error('Error loading file:', err)
        setError('Error loading BPMN file')
      }
    }
    reader.readAsText(file)
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Edit3 className="h-5 w-5" />
            Editor BPMN (Simple)
            <Badge variant={isViewMode ? "secondary" : "default"}>
              {isViewMode ? "Solo Lectura" : "Edición"}
            </Badge>
          </CardTitle>
          <div className="flex items-center gap-2">
            {!readonly && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSave}
                  disabled={isLoading}
                >
                  <Save className="h-4 w-4 mr-2" />
                  Guardar
                </Button>
                
                <input
                  type="file"
                  accept=".bpmn,.xml"
                  onChange={handleFileUpload}
                  className="hidden"
                  id="bpmn-upload-simple"
                />
                <label htmlFor="bpmn-upload-simple">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={isLoading}
                  >
                    <Upload className="h-4 w-4 mr-2" />
                    Cargar
                  </Button>
                </label>
              </>
            )}
            
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownload}
              disabled={isLoading}
            >
              <Download className="h-4 w-4 mr-2" />
              Descargar
            </Button>
          </div>
        </div>
      </CardHeader>
      
      <CardContent>
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-red-700 flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />
            {error}
          </div>
        )}
        
        <div 
          ref={containerRef}
          style={{ height, minHeight: '400px' }}
          className="border border-gray-200 rounded-md bg-white relative overflow-hidden"
        >
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-white bg-opacity-90 z-10">
              <div className="text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
                <p className="text-sm text-gray-600">
                  Cargando editor BPMN simple...
                </p>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}