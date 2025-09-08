"use client"

import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Download, Upload, Save, Eye, Edit3, AlertCircle } from 'lucide-react'

interface BPMNEditorIframeProps {
  initialBpmn?: string
  onSave?: (bpmnXml: string) => void
  readonly?: boolean
  height?: string
}

export function BPMNEditorIframe({ 
  initialBpmn, 
  onSave, 
  readonly = false, 
  height = "500px" 
}: BPMNEditorIframeProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [currentBpmn, setCurrentBpmn] = useState<string>("")

  useEffect(() => {
    const iframe = iframeRef.current
    if (!iframe) return

    const setupIframe = () => {
      const iframeDoc = iframe.contentDocument
      if (!iframeDoc) return

      // Create HTML content for the iframe
      const iframeHtml = `
        <!DOCTYPE html>
        <html>
        <head>
          <title>BPMN Editor</title>
          <script src="https://unpkg.com/bpmn-js@18/dist/bpmn-modeler.development.js"></script>
          <style>
            body { 
              margin: 0; 
              padding: 0; 
              font-family: Arial, sans-serif;
              background: #f9fafb;
            }
            #canvas { 
              width: 100%; 
              height: ${height}; 
              min-height: 400px;
              background: white;
              border: 1px solid #e5e7eb;
            }
            .loading {
              display: flex;
              align-items: center;
              justify-content: center;
              height: 100vh;
              font-size: 14px;
              color: #6b7280;
            }
            .error {
              display: flex;
              align-items: center;
              justify-content: center;
              height: 100vh;
              font-size: 14px;
              color: #dc2626;
              padding: 20px;
              text-align: center;
            }
          </style>
        </head>
        <body>
          <div id="loading" class="loading">Cargando editor BPMN...</div>
          <div id="canvas" style="display: none;"></div>
          <div id="error" class="error" style="display: none;"></div>
          
          <script>
            window.bpmnModeler = null;
            window.currentBpmn = '';
            
            function showLoading() {
              document.getElementById('loading').style.display = 'flex';
              document.getElementById('canvas').style.display = 'none';
              document.getElementById('error').style.display = 'none';
            }
            
            function showEditor() {
              document.getElementById('loading').style.display = 'none';
              document.getElementById('canvas').style.display = 'block';
              document.getElementById('error').style.display = 'none';
            }
            
            function showError(message) {
              document.getElementById('loading').style.display = 'none';
              document.getElementById('canvas').style.display = 'none';
              document.getElementById('error').style.display = 'flex';
              document.getElementById('error').textContent = message;
            }
            
            function initializeBpmn() {
              try {
                showLoading();
                
                if (typeof BpmnJS === 'undefined') {
                  throw new Error('BPMN-JS library not loaded');
                }
                
                window.bpmnModeler = new BpmnJS({
                  container: '#canvas',
                  width: '100%',
                  height: '100%'
                });
                
                window.bpmnModeler.on('import.done', function() {
                  console.log('BPMN import completed successfully');
                  showEditor();
                  // Notify parent that loading is complete
                  window.parent.postMessage({ type: 'bpmn-loaded' }, '*');
                });
                
                window.bpmnModeler.on('import.error', function(event) {
                  console.error('BPMN import error:', event.error);
                  showError('Error cargando diagrama BPMN: ' + event.error.message);
                  window.parent.postMessage({ type: 'bpmn-error', error: event.error.message }, '*');
                });
                
                // Load initial BPMN
                const initialBpmn = ${JSON.stringify(initialBpmn || getDefaultBpmn())};
                loadBpmn(initialBpmn);
                
              } catch (error) {
                console.error('Error initializing BPMN:', error);
                showError('Error inicializando editor: ' + error.message);
                window.parent.postMessage({ type: 'bpmn-error', error: error.message }, '*');
              }
            }
            
            function loadBpmn(xml) {
              if (!window.bpmnModeler || !xml) return;
              
              window.bpmnModeler.importXML(xml).then(function() {
                window.currentBpmn = xml;
                console.log('BPMN loaded successfully');
              }).catch(function(error) {
                console.error('Error loading BPMN:', error);
                showError('Error cargando BPMN: ' + error.message);
              });
            }
            
            function saveBpmn() {
              if (!window.bpmnModeler) {
                console.error('BPMN modeler not initialized');
                return;
              }
              
              window.bpmnModeler.saveXML({ format: true }).then(function(result) {
                window.currentBpmn = result.xml;
                window.parent.postMessage({ 
                  type: 'bpmn-saved', 
                  xml: result.xml 
                }, '*');
              }).catch(function(error) {
                console.error('Error saving BPMN:', error);
                window.parent.postMessage({ 
                  type: 'bpmn-error', 
                  error: error.message 
                }, '*');
              });
            }
            
            function zoomFit() {
              if (!window.bpmnModeler) return;
              try {
                const canvas = window.bpmnModeler.get('canvas');
                canvas.zoom('fit-viewport');
              } catch (error) {
                console.warn('Could not zoom fit:', error);
              }
            }
            
            // Listen for messages from parent
            window.addEventListener('message', function(event) {
              if (event.source !== window.parent) return;
              
              switch (event.data.type) {
                case 'load-bpmn':
                  loadBpmn(event.data.xml);
                  break;
                case 'save-bpmn':
                  saveBpmn();
                  break;
                case 'zoom-fit':
                  zoomFit();
                  break;
              }
            });
            
            // Initialize when DOM is ready and BPMN-JS is loaded
            function checkAndInit() {
              if (typeof BpmnJS !== 'undefined') {
                initializeBpmn();
              } else {
                setTimeout(checkAndInit, 100);
              }
            }
            
            document.addEventListener('DOMContentLoaded', checkAndInit);
            
            // Fallback initialization
            setTimeout(checkAndInit, 500);
          </script>
        </body>
        </html>
      `

      // Write the HTML to the iframe
      iframeDoc.open()
      iframeDoc.write(iframeHtml)
      iframeDoc.close()
    }

    // Set up iframe when it loads
    iframe.onload = setupIframe
    
    // If iframe is already loaded, set it up immediately
    if (iframe.contentDocument?.readyState === 'complete') {
      setupIframe()
    }

    // Listen for messages from iframe
    const handleMessage = (event: MessageEvent) => {
      if (event.source !== iframe.contentWindow) return
      
      switch (event.data.type) {
        case 'bpmn-loaded':
          setIsLoading(false)
          setError(null)
          break
        case 'bpmn-error':
          setError(event.data.error)
          setIsLoading(false)
          break
        case 'bpmn-saved':
          setCurrentBpmn(event.data.xml)
          onSave?.(event.data.xml)
          break
      }
    }

    window.addEventListener('message', handleMessage)

    return () => {
      window.removeEventListener('message', handleMessage)
    }
  }, [initialBpmn, height, onSave])

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

  const handleSave = () => {
    if (iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.postMessage({ type: 'save-bpmn' }, '*')
    }
  }

  const handleDownload = () => {
    if (currentBpmn) {
      const blob = new Blob([currentBpmn], { type: 'application/xml' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'diagram.bpmn'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } else {
      // Request current BPMN from iframe first
      handleSave()
      setTimeout(() => {
        if (currentBpmn) {
          handleDownload()
        }
      }, 500)
    }
  }

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file || !iframeRef.current?.contentWindow) return

    const reader = new FileReader()
    reader.onload = (e) => {
      const xml = e.target?.result as string
      if (xml && iframeRef.current?.contentWindow) {
        iframeRef.current.contentWindow.postMessage({ 
          type: 'load-bpmn', 
          xml: xml 
        }, '*')
        setCurrentBpmn(xml)
        setError(null)
      }
    }
    reader.readAsText(file)
  }

  const handleZoomFit = () => {
    if (iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.postMessage({ type: 'zoom-fit' }, '*')
    }
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Edit3 className="h-5 w-5" />
            Editor BPMN (Aislado)
            <Badge variant="default">
              Sin Conflictos DOM
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
                  id="bpmn-upload-iframe"
                />
                <label htmlFor="bpmn-upload-iframe">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={isLoading}
                    asChild
                  >
                    <span>
                      <Upload className="h-4 w-4 mr-2" />
                      Cargar
                    </span>
                  </Button>
                </label>
              </>
            )}
            
            <Button
              variant="outline"
              size="sm"
              onClick={handleZoomFit}
              disabled={isLoading}
            >
              <Eye className="h-4 w-4 mr-2" />
              Ajustar
            </Button>
            
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
        
        <div className="relative">
          <iframe
            ref={iframeRef}
            style={{ 
              width: '100%', 
              height: height, 
              minHeight: '400px',
              border: '1px solid #e5e7eb',
              borderRadius: '6px'
            }}
            title="BPMN Editor"
          />
          
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-white bg-opacity-90 z-10 rounded-md">
              <div className="text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
                <p className="text-sm text-gray-600">
                  Cargando editor BPMN aislado...
                </p>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}