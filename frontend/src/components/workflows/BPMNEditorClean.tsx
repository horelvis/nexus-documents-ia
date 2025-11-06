"use client"

import { useEffect, useRef, useState, useLayoutEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Download, Upload, Save, Eye, Edit3 } from 'lucide-react'

// Importaciones de bpmn-js - globals para evitar re-imports
let BpmnModeler: any = null
let BpmnViewer: any = null
let isLoadingLibs = false

interface BPMNEditorCleanProps {
  initialBpmn?: string
  onSave?: (bpmnXml: string) => void
  readonly?: boolean
  height?: string
}

export function BPMNEditorClean({ 
  initialBpmn, 
  onSave, 
  readonly = false, 
  height = "500px" 
}: BPMNEditorCleanProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const modelerRef = useRef<any>(null)
  const isMountedRef = useRef(true) // Flag para controlar si el componente está montado
  const loadingTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [currentBpmn, setCurrentBpmn] = useState<string>("")
  const [isViewMode, setIsViewMode] = useState(readonly)
  const [bpmnLibsLoaded, setBpmnLibsLoaded] = useState(false)

  // Cargar bpmn-js dinámicamente una sola vez
  useEffect(() => {
    // Si ya están cargados globalmente, usarlos directamente
    if (BpmnModeler && BpmnViewer) {
      console.log('✅ BPMN libs already loaded globally')
      setBpmnLibsLoaded(true)
      return
    }
    
    if (bpmnLibsLoaded || isLoadingLibs) return

    const loadBpmnJs = async () => {
      try {
        console.log('🔄 Starting to load bpmn-js libraries...')
        if (typeof window === 'undefined') {
          console.log('❌ Window is undefined, skipping load')
          return
        }

        // Set a timeout to prevent infinite loading
        loadingTimeoutRef.current = setTimeout(() => {
          if (isMountedRef.current && !bpmnLibsLoaded) {
            console.log('⏰ Loading timeout reached')
            setError('Tiempo de carga agotado. Recarga la página.')
            setIsLoading(false)
            isLoadingLibs = false
          }
        }, 15000) // 15 second timeout

        isLoadingLibs = true
        console.log('📦 Loading bpmn-js modules...')
        
        // Try different import approaches
        try {
          const modelerModule = await import('bpmn-js/lib/Modeler')
          const viewerModule = await import('bpmn-js/lib/Viewer')
          
          console.log('✅ Modules loaded:', { modelerModule, viewerModule })
          BpmnModeler = modelerModule.default
          BpmnViewer = viewerModule.default
        } catch (importError) {
          console.log('❌ Direct import failed, trying alternative approach...')
          // Fallback: try to import the full package
          const bpmnJs = await import('bpmn-js')
          console.log('✅ Full bpmn-js loaded:', bpmnJs)
          BpmnModeler = (bpmnJs as any).default || bpmnJs
          BpmnViewer = (bpmnJs as any).Viewer || BpmnModeler
        }
        
        console.log('✅ Classes assigned:', { 
          BpmnModeler: !!BpmnModeler, 
          BpmnViewer: !!BpmnViewer,
          BpmnModelerType: typeof BpmnModeler,
          BpmnViewerType: typeof BpmnViewer
        })
        
        if (isMountedRef.current && BpmnModeler && BpmnViewer) {
          console.log('✅ Component still mounted, setting bpmnLibsLoaded = true')
          // Clear timeout on success
          if (loadingTimeoutRef.current) {
            clearTimeout(loadingTimeoutRef.current)
            loadingTimeoutRef.current = null
          }
          setBpmnLibsLoaded(true)
        } else {
          console.log('❌ Component unmounted or classes not loaded properly')
          if (!BpmnModeler || !BpmnViewer) {
            throw new Error('BPMN classes not loaded properly')
          }
        }
        
      } catch (err) {
        console.error('❌ Error loading bpmn-js:', err)
        console.error('❌ Error details:', {
          message: err.message,
          stack: err.stack,
          name: err.name
        })
        if (isMountedRef.current) {
          setError(`Error cargando el editor BPMN: ${err.message}`)
          setIsLoading(false)
        }
      } finally {
        isLoadingLibs = false
        if (loadingTimeoutRef.current) {
          clearTimeout(loadingTimeoutRef.current)
          loadingTimeoutRef.current = null
        }
      }
    }

    loadBpmnJs()
  }, [])

  // Limpieza al desmontar - usando useLayoutEffect para orden correcto
  useLayoutEffect(() => {
    return () => {
      isMountedRef.current = false
      if (loadingTimeoutRef.current) {
        clearTimeout(loadingTimeoutRef.current)
        loadingTimeoutRef.current = null
      }
      cleanupModeler()
    }
  }, [])

  // Inicializar BPMN cuando todo esté listo
  useEffect(() => {
    console.log('🔍 Checking initialization conditions:', {
      bpmnLibsLoaded,
      containerExists: !!containerRef.current,
      isMounted: isMountedRef.current,
      isViewMode
    })
    
    if (!bpmnLibsLoaded) {
      console.log('⏳ Waiting for BPMN libs to load...')
      return
    }
    if (!containerRef.current) {
      console.log('⏳ Waiting for container ref...')
      return
    }
    if (!isMountedRef.current) {
      console.log('❌ Component not mounted, skipping initialization')
      return
    }
    
    console.log('🚀 All conditions met, initializing BPMN...')
    initializeBpmn()
  }, [bpmnLibsLoaded, isViewMode])

  // Manejar cambios en initialBpmn
  useEffect(() => {
    if (bpmnLibsLoaded && modelerRef.current && initialBpmn && initialBpmn !== currentBpmn && isMountedRef.current) {
      updateBpmn(initialBpmn)
    }
  }, [initialBpmn, bpmnLibsLoaded, currentBpmn])

  const cleanupModeler = () => {
    if (modelerRef.current) {
      try {
        // Usar detach() para desconectar del DOM antes de destroy()
        if (typeof modelerRef.current.detach === 'function') {
          modelerRef.current.detach()
        }
        
        // Limpiar eventos
        modelerRef.current.off('import.done')
        modelerRef.current.off('import.error')
        
        // Destruir instancia
        modelerRef.current.destroy()
      } catch (cleanupError) {
        console.warn('Error during BPMN cleanup:', cleanupError)
      } finally {
        modelerRef.current = null
      }
    }
  }

  const initializeBpmn = async () => {
    console.log('🔧 initializeBpmn starting...', {
      containerExists: !!containerRef.current,
      BpmnModelerExists: !!BpmnModeler,
      BpmnViewerExists: !!BpmnViewer,
      isMounted: isMountedRef.current
    })
    
    if (!containerRef.current || !BpmnModeler || !BpmnViewer || !isMountedRef.current) {
      console.log('❌ Missing requirements for initialization')
      return
    }

    try {
      console.log('🔄 Setting loading state...')
      if (isMountedRef.current) {
        setIsLoading(true)
        setError(null)
      }

      // Limpiar instancia anterior
      cleanupModeler()

      // Asegurar que el contenedor esté limpio
      if (containerRef.current && containerRef.current.children.length > 0) {
        // Verificar si los hijos existen antes de removerlos
        while (containerRef.current.firstChild) {
          containerRef.current.removeChild(containerRef.current.firstChild)
        }
      }
      
      // Verificar que el componente siga montado después de la limpieza
      if (!isMountedRef.current || !containerRef.current) return

      // Pequeña pausa para asegurar que el DOM esté estable
      await new Promise(resolve => setTimeout(resolve, 50))

      // Verificar nuevamente después de la pausa
      if (!isMountedRef.current || !containerRef.current) return

      // Crear nueva instancia sin pasarle el container inicialmente
      const BpmnClass = isViewMode ? BpmnViewer : BpmnModeler
      
      modelerRef.current = new BpmnClass()

      // Usar attachTo() para conectar al DOM de forma segura
      modelerRef.current.attachTo(containerRef.current)

      // Configurar eventos solo si el componente sigue montado
      if (isMountedRef.current) {
        modelerRef.current.on('import.done', () => {
          console.log('BPMN import completed with attachTo pattern')
          if (isMountedRef.current) {
            setIsLoading(false)
            
            // Auto zoom con delay
            setTimeout(() => {
              if (isMountedRef.current && modelerRef.current) {
                try {
                  const canvas = modelerRef.current.get('canvas')
                  if (canvas && typeof canvas.zoom === 'function') {
                    canvas.zoom('fit-viewport')
                  }
                } catch (zoomErr) {
                  console.warn('Could not auto-zoom:', zoomErr)
                }
              }
            }, 200)
          }
        })

        modelerRef.current.on('import.error', (event: any) => {
          console.error('BPMN import error with attachTo pattern:', event.error)
          if (isMountedRef.current) {
            setError(`Error importando BPMN: ${event.error.message}`)
            setIsLoading(false)
          }
        })
      }

      // Cargar BPMN inicial si el componente sigue montado
      if (isMountedRef.current) {
        const bpmnToLoad = initialBpmn || getDefaultBpmn()
        await modelerRef.current.importXML(bpmnToLoad)
        
        if (isMountedRef.current) {
          setCurrentBpmn(bpmnToLoad)
        }
      }

    } catch (err: any) {
      console.error('Error inicializando BPMN con attachTo pattern:', err)
      if (isMountedRef.current) {
        setError(`Error cargando el diagrama: ${err.message}`)
        setIsLoading(false)
        cleanupModeler()
      }
    }
  }

  const updateBpmn = async (newBpmn: string) => {
    if (!modelerRef.current || !newBpmn || !isMountedRef.current) return

    try {
      if (isMountedRef.current) {
        setIsLoading(true)
      }
      
      await modelerRef.current.importXML(newBpmn)
      
      if (isMountedRef.current) {
        setCurrentBpmn(newBpmn)
        
        // Auto zoom después de actualizar
        setTimeout(() => {
          if (isMountedRef.current && modelerRef.current) {
            try {
              const canvas = modelerRef.current.get('canvas')
              if (canvas && typeof canvas.zoom === 'function') {
                canvas.zoom('fit-viewport')
              }
            } catch (zoomErr) {
              console.warn('Could not auto-zoom after update:', zoomErr)
            }
          }
        }, 200)
      }
      
    } catch (err: any) {
      console.error('Error updating BPMN:', err)
      if (isMountedRef.current) {
        setError(`Error actualizando el diagrama: ${err.message}`)
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false)
      }
    }
  }

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
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds height="36" width="36" x="412" y="240"/>
      </bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn2:definitions>`
  }

  const handleSave = async () => {
    if (!modelerRef.current || !isMountedRef.current) return

    try {
      const result = await modelerRef.current.saveXML({ format: true })
      const xml = result.xml
      if (isMountedRef.current) {
        setCurrentBpmn(xml)
        onSave?.(xml)
      }
    } catch (err: any) {
      console.error('Error guardando BPMN:', err)
      if (isMountedRef.current) {
        setError('Error guardando el diagrama')
      }
    }
  }

  const handleDownload = async () => {
    if (!modelerRef.current || !isMountedRef.current) return

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
      console.error('Error descargando BPMN:', err)
      if (isMountedRef.current) {
        setError('Error descargando el diagrama')
      }
    }
  }

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file || !isMountedRef.current) return

    const reader = new FileReader()
    reader.onload = async (e) => {
      try {
        const xml = e.target?.result as string
        await updateBpmn(xml)
        if (isMountedRef.current) {
          setError(null)
        }
      } catch (err: any) {
        console.error('Error cargando archivo:', err)
        if (isMountedRef.current) {
          setError('Error cargando el archivo BPMN')
        }
      }
    }
    reader.readAsText(file)
  }

  const toggleViewMode = () => {
    if (isMountedRef.current) {
      setIsViewMode(!isViewMode)
    }
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Edit3 className="h-5 w-5" />
            Editor BPMN 2.0 (Limpio)
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
                  onClick={toggleViewMode}
                  disabled={isLoading}
                >
                  {isViewMode ? <Edit3 className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  {isViewMode ? "Editar" : "Vista"}
                </Button>
                
                {!isViewMode && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleSave}
                    disabled={isLoading}
                  >
                    <Save className="h-4 w-4 mr-2" />
                    Guardar
                  </Button>
                )}
                
                <input
                  type="file"
                  accept=".bpmn,.xml"
                  onChange={handleFileUpload}
                  className="hidden"
                  id="bpmn-upload-clean"
                />
                <label htmlFor="bpmn-upload-clean">
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
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-red-700">
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
                  {bpmnLibsLoaded ? 'Cargando diagrama BPMN...' : 'Cargando editor BPMN limpio...'}
                </p>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}