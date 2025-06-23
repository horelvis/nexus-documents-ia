"use client"

import { useState, useRef, useEffect } from "react"
import { 
  IconSignature, 
  IconCalendar, 
  IconUser, 
  IconMail,
  IconFileText,
  IconX,
  IconGripVertical,
  IconResize,
  IconTrash,
  IconCheck,
  IconLoader2,
  IconChevronLeft,
  IconChevronRight,
  IconZoomIn,
  IconZoomOut
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import { useDocumentService } from "@/lib/services/document.service"
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

interface SignatureField {
  id: string
  type: 'signature'
  signer: string
  required: boolean
  x: number
  y: number
  width: number
  height: number
  page: number
  label?: string
  aiSuggested?: boolean
}

interface Signer {
  id: string
  email: string
  name: string
  color: string
}

interface SignaturePlacementEditorProps {
  documentId: string
  signers: Signer[]
  onFieldsChange: (fields: SignatureField[]) => void
  initialFields?: SignatureField[]
}

const FIELD_TYPES = [
  { value: 'signature', label: 'Signature', icon: IconSignature }
]

export function SignaturePlacementEditor({
  documentId,
  signers,
  onFieldsChange,
  initialFields = []
}: SignaturePlacementEditorProps) {
  const [fields, setFields] = useState<SignatureField[]>(initialFields)
  const [selectedField, setSelectedField] = useState<string | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [scale, setScale] = useState(0.8)
  const [isDragging, setIsDragging] = useState(false)
  const [draggedFieldType, setDraggedFieldType] = useState<string | null>(null)
  const [draggedFieldId, setDraggedFieldId] = useState<string | null>(null)
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })
  const [isResizing, setIsResizing] = useState(false)
  const [resizeStart, setResizeStart] = useState({ x: 0, y: 0, width: 0, height: 0 })
  const [selectedSigner, setSelectedSigner] = useState<string>(signers[0]?.id || '')
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [isLoadingPdf, setIsLoadingPdf] = useState(true)
  
  const containerRef = useRef<HTMLDivElement>(null)
  const documentService = useDocumentService()

  // Load PDF document
  useEffect(() => {
    if (documentId) {
      loadPdf()
    }
    
    return () => {
      // Cleanup blob URL
      if (pdfUrl && pdfUrl.startsWith('blob:')) {
        URL.revokeObjectURL(pdfUrl)
      }
    }
  }, [documentId])

  const loadPdf = async () => {
    setIsLoadingPdf(true)
    try {
      // Download the document to get a blob URL for the PDF viewer
      const result = await documentService.downloadDocument(documentId)
      
      if ('error' in result) {
        console.error('Failed to load document:', result.error)
        return
      }
      
      // Create blob URL for PDF viewer
      const url = URL.createObjectURL(result.blob)
      setPdfUrl(url)
    } catch (error) {
      console.error('Failed to load PDF:', error)
    } finally {
      setIsLoadingPdf(false)
    }
  }

  const handleDragStart = (e: React.DragEvent, fieldType: string) => {
    setIsDragging(true)
    setDraggedFieldType(fieldType)
    e.dataTransfer.effectAllowed = 'copy'
  }

  const handleDragEnd = () => {
    setIsDragging(false)
    setDraggedFieldType(null)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)

    if (!draggedFieldType || !containerRef.current) return

    // Find the PDF page element
    const pdfPage = containerRef.current.querySelector('.react-pdf__Page') as HTMLElement
    if (!pdfPage) return

    const rect = pdfPage.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top

    const newField: SignatureField = {
      id: `field-${Date.now()}`,
      type: 'signature',
      signer: selectedSigner,
      required: true,
      x,
      y,
      width: 200,
      height: 50,
      page: currentPage,
      label: 'Signature'
    }

    const updatedFields = [...fields, newField]
    setFields(updatedFields)
    onFieldsChange(updatedFields)
    setSelectedField(newField.id)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }

  const handleFieldClick = (fieldId: string) => {
    setSelectedField(fieldId)
  }
  
  const handleFieldMouseDown = (e: React.MouseEvent, field: SignatureField) => {
    e.preventDefault()
    e.stopPropagation()
    
    const rect = (e.target as HTMLElement).getBoundingClientRect()
    setDraggedFieldId(field.id)
    setDragOffset({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top
    })
  }
  
  const handleMouseMove = (e: MouseEvent) => {
    if (!draggedFieldId) return
    
    const pdfPage = containerRef.current?.querySelector('.react-pdf__Page') as HTMLElement
    if (!pdfPage) return
    
    const rect = pdfPage.getBoundingClientRect()
    const x = e.clientX - rect.left - dragOffset.x
    const y = e.clientY - rect.top - dragOffset.y
    
    // Update field position
    const updatedFields = fields.map(field => 
      field.id === draggedFieldId 
        ? { ...field, x: Math.max(0, x), y: Math.max(0, y) }
        : field
    )
    
    setFields(updatedFields)
    onFieldsChange(updatedFields)
  }
  
  const handleMouseUp = () => {
    setDraggedFieldId(null)
    setDragOffset({ x: 0, y: 0 })
    setIsResizing(false)
    setResizeStart({ x: 0, y: 0, width: 0, height: 0 })
  }
  
  const handleResizeMouseDown = (e: React.MouseEvent, field: SignatureField) => {
    e.preventDefault()
    e.stopPropagation()
    
    setSelectedField(field.id)
    setIsResizing(true)
    setResizeStart({
      x: e.clientX,
      y: e.clientY,
      width: field.width,
      height: field.height
    })
  }
  
  const handleResizeMove = (e: MouseEvent) => {
    if (!isResizing || !selectedField) return
    
    const deltaX = e.clientX - resizeStart.x
    const deltaY = e.clientY - resizeStart.y
    
    const updatedFields = fields.map(field => 
      field.id === selectedField 
        ? { 
            ...field, 
            width: Math.max(100, resizeStart.width + deltaX),
            height: Math.max(30, resizeStart.height + deltaY)
          }
        : field
    )
    
    setFields(updatedFields)
    onFieldsChange(updatedFields)
  }
  
  // Add mouse event listeners
  useEffect(() => {
    if (draggedFieldId || isResizing) {
      const moveHandler = isResizing ? handleResizeMove : handleMouseMove
      document.addEventListener('mousemove', moveHandler)
      document.addEventListener('mouseup', handleMouseUp)
      
      return () => {
        document.removeEventListener('mousemove', moveHandler)
        document.removeEventListener('mouseup', handleMouseUp)
      }
    }
  }, [draggedFieldId, isResizing, dragOffset, resizeStart])

  const handleFieldDelete = (fieldId: string) => {
    const updatedFields = fields.filter(f => f.id !== fieldId)
    setFields(updatedFields)
    onFieldsChange(updatedFields)
    setSelectedField(null)
  }

  const handleFieldUpdate = (fieldId: string, updates: Partial<SignatureField>) => {
    const updatedFields = fields.map(f => 
      f.id === fieldId ? { ...f, ...updates } : f
    )
    setFields(updatedFields)
    onFieldsChange(updatedFields)
  }

  const handleFieldMove = (fieldId: string, deltaX: number, deltaY: number) => {
    handleFieldUpdate(fieldId, {
      x: fields.find(f => f.id === fieldId)!.x + deltaX,
      y: fields.find(f => f.id === fieldId)!.y + deltaY
    })
  }

  const handleFieldResize = (fieldId: string, deltaWidth: number, deltaHeight: number) => {
    const field = fields.find(f => f.id === fieldId)!
    handleFieldUpdate(fieldId, {
      width: Math.max(100, field.width + deltaWidth),
      height: Math.max(30, field.height + deltaHeight)
    })
  }

  const getSignerColor = (signerId: string) => {
    return signers.find(s => s.id === signerId)?.color || '#666'
  }

  const getFieldIcon = (type: string) => {
    const fieldType = FIELD_TYPES.find(ft => ft.value === type)
    return fieldType?.icon || IconFileText
  }

  return (
    <div className="flex gap-4 h-[800px]">
      {/* Sidebar */}
      <Card className="w-80 p-4 flex flex-col">
        <h3 className="font-semibold mb-4">Signature Fields</h3>
        
        {/* Signer Selection */}
        <div className="mb-4">
          <Label>Current Signer</Label>
          <Select value={selectedSigner} onValueChange={setSelectedSigner}>
            <SelectTrigger className="mt-1">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {signers.map(signer => (
                <SelectItem key={signer.id} value={signer.id}>
                  <div className="flex items-center gap-2">
                    <div 
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: signer.color }}
                    />
                    <span>{signer.name}</span>
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Separator className="mb-4" />

        {/* Signature Field */}
        <div className="space-y-2 mb-4">
          <Label>Drag to add signature field</Label>
          <div
            draggable
            onDragStart={(e) => handleDragStart(e, 'signature')}
            onDragEnd={handleDragEnd}
            className={cn(
              "flex items-center gap-2 p-3 border rounded-md cursor-move",
              "hover:bg-accent hover:border-accent-foreground/20",
              "transition-colors",
              isDragging && "opacity-50"
            )}
          >
            <IconSignature className="h-4 w-4" />
            <span className="text-sm">Signature Field</span>
            <IconGripVertical className="h-4 w-4 ml-auto text-muted-foreground" />
          </div>
        </div>

        <Separator className="mb-4" />

        {/* Field List */}
        <div className="flex-1 overflow-y-auto">
          <Label className="mb-2 block">Placed Fields</Label>
          <div className="space-y-2">
            {fields.filter(f => f.page === currentPage).map(field => {
              const signer = signers.find(s => s.id === field.signer)
              const Icon = getFieldIcon(field.type)
              
              return (
                <div
                  key={field.id}
                  onClick={() => handleFieldClick(field.id)}
                  className={cn(
                    "p-2 border rounded-md cursor-pointer",
                    "hover:bg-accent",
                    selectedField === field.id && "border-primary bg-accent"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <Icon className="h-3 w-3" />
                    <span className="text-sm flex-1">{field.label}</span>
                    <div className="flex items-center gap-1">
                      {field.aiSuggested && (
                        <Badge variant="secondary" className="text-xs">
                          AI
                        </Badge>
                      )}
                      <Badge 
                        variant="outline"
                        style={{ 
                          borderColor: signer?.color,
                          color: signer?.color 
                        }}
                        className="text-xs"
                      >
                        {signer?.name}
                      </Badge>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Selected Field Properties */}
        {selectedField && (
          <div className="mt-4 pt-4 border-t space-y-3">
            <h4 className="font-medium text-sm">Field Properties</h4>
            {(() => {
              const field = fields.find(f => f.id === selectedField)
              if (!field) return null
              
              return (
                <>
                  <div>
                    <Label className="text-xs">Label</Label>
                    <Input
                      value={field.label || ''}
                      onChange={(e) => handleFieldUpdate(field.id, { label: e.target.value })}
                      className="mt-1 h-8 text-sm"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">Required</Label>
                    <Button
                      size="sm"
                      variant={field.required ? "default" : "outline"}
                      onClick={() => handleFieldUpdate(field.id, { required: !field.required })}
                      className="h-7"
                    >
                      {field.required ? <IconCheck className="h-3 w-3" /> : <IconX className="h-3 w-3" />}
                    </Button>
                  </div>
                  {field.aiSuggested && field.confidence && (
                    <div>
                      <Label className="text-xs">AI Confidence</Label>
                      <div className="mt-1">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-gray-200 rounded-full h-2">
                            <div 
                              className="bg-primary rounded-full h-2"
                              style={{ width: `${field.confidence * 100}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {Math.round(field.confidence * 100)}%
                          </span>
                        </div>
                        {field.reason && (
                          <p className="text-xs text-muted-foreground mt-1">
                            {field.reason}
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => handleFieldDelete(field.id)}
                    className="w-full"
                  >
                    <IconTrash className="h-3 w-3 mr-1" />
                    Delete Field
                  </Button>
                </>
              )
            })()}
          </div>
        )}
      </Card>

      {/* Document Viewer */}
      <Card className="flex-1 overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
            >
              Previous
            </Button>
            <span className="text-sm">
              Page {currentPage} of {totalPages}
            </span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
            >
              Next
            </Button>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setScale(Math.max(0.5, scale - 0.1))}
            >
              -
            </Button>
            <span className="text-sm w-16 text-center">{Math.round(scale * 100)}%</span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setScale(Math.min(2, scale + 0.1))}
            >
              +
            </Button>
          </div>
        </div>

        <div 
          ref={containerRef}
          className="relative overflow-auto flex-1 bg-gray-100 p-4"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          {isLoadingPdf ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <IconLoader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
                <p className="text-muted-foreground">Loading document...</p>
              </div>
            </div>
          ) : pdfUrl ? (
            <div className="relative inline-block">
              {/* PDF Document */}
              <Document
                file={pdfUrl}
                onLoadSuccess={(pdf) => setTotalPages(pdf.numPages)}
                loading={
                  <div className="flex items-center justify-center p-8">
                    <IconLoader2 className="h-6 w-6 animate-spin" />
                  </div>
                }
                error={
                  <div className="text-center p-8">
                    <p className="text-destructive">Failed to load PDF</p>
                  </div>
                }
              >
                <div className="relative bg-white shadow-lg">
                  <Page
                    pageNumber={currentPage}
                    scale={scale}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                  />
                  
                  {/* Overlay for signature fields */}
                  <div className="absolute inset-0">
                  {/* Render fields */}
                  {fields.filter(f => f.page === currentPage).map(field => {
                    const signer = signers.find(s => s.id === field.signer)
                    const Icon = getFieldIcon(field.type)
                    
                    return (
                      <div
                        key={field.id}
                        onClick={() => handleFieldClick(field.id)}
                        onMouseDown={(e) => handleFieldMouseDown(e, field)}
                        style={{
                          position: 'absolute',
                          left: field.x,
                          top: field.y,
                          width: field.width,
                          height: field.height,
                          border: `2px solid ${signer?.color || '#666'}`,
                          backgroundColor: `${signer?.color}20` || '#66666620',
                          cursor: draggedFieldId === field.id ? 'grabbing' : 'grab',
                          pointerEvents: 'auto',
                          userSelect: 'none'
                        }}
                        className={cn(
                          "flex items-center justify-center gap-2 rounded transition-shadow",
                          "hover:ring-2 hover:ring-offset-1",
                          selectedField === field.id && "ring-2 ring-primary",
                          draggedFieldId === field.id && "opacity-80 shadow-lg"
                        )}
                      >
                        <Icon className="h-4 w-4" style={{ color: signer?.color }} />
                        <span className="text-xs font-medium" style={{ color: signer?.color }}>
                          {field.label}
                        </span>
                        {field.aiSuggested && (
                          <Badge 
                            variant="secondary" 
                            className="absolute -top-2 -right-2 text-xs px-1 py-0 h-5"
                          >
                            AI
                          </Badge>
                        )}
                        
                        {/* Resize handle */}
                        {selectedField === field.id && (
                          <div
                            className="absolute bottom-0 right-0 w-4 h-4 bg-primary cursor-se-resize rounded-tl"
                            onMouseDown={(e) => handleResizeMouseDown(e, field)}
                          >
                            <IconResize className="h-3 w-3 text-white" />
                          </div>
                        )}
                      </div>
                    )
                  })}
                  </div>
                </div>
              </Document>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-muted-foreground">Failed to load document</p>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}