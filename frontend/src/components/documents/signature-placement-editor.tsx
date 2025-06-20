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
  IconCheck
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

interface SignatureField {
  id: string
  type: 'signature' | 'date' | 'text' | 'name' | 'email'
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
  documentUrl: string
  signers: Signer[]
  onFieldsChange: (fields: SignatureField[]) => void
  initialFields?: SignatureField[]
}

const FIELD_TYPES = [
  { value: 'signature', label: 'Signature', icon: IconSignature },
  { value: 'date', label: 'Date', icon: IconCalendar },
  { value: 'name', label: 'Name', icon: IconUser },
  { value: 'email', label: 'Email', icon: IconMail },
  { value: 'text', label: 'Text Field', icon: IconFileText },
]

export function SignaturePlacementEditor({
  documentUrl,
  signers,
  onFieldsChange,
  initialFields = []
}: SignaturePlacementEditorProps) {
  const [fields, setFields] = useState<SignatureField[]>(initialFields)
  const [selectedField, setSelectedField] = useState<string | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [scale, setScale] = useState(1)
  const [isDragging, setIsDragging] = useState(false)
  const [draggedFieldType, setDraggedFieldType] = useState<string | null>(null)
  const [selectedSigner, setSelectedSigner] = useState<string>(signers[0]?.id || '')
  
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Load PDF and render current page
  useEffect(() => {
    if (documentUrl) {
      loadPdfPage()
    }
  }, [documentUrl, currentPage, scale])

  const loadPdfPage = async () => {
    // This is a simplified version - in production you'd use PDF.js
    // For now, we'll use the document as an image
    const canvas = canvasRef.current
    if (!canvas || !documentUrl) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // For now, display a placeholder
    // TODO: Integrate PDF.js for actual PDF rendering
    canvas.width = 816 // Letter size at 96 DPI
    canvas.height = 1056
    
    ctx.fillStyle = '#f5f5f5'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    
    ctx.strokeStyle = '#ddd'
    ctx.strokeRect(20, 20, canvas.width - 40, canvas.height - 40)
    
    ctx.fillStyle = '#666'
    ctx.font = '16px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('Document Preview', canvas.width / 2, 50)
    ctx.fillText('(Drag signature fields here)', canvas.width / 2, canvas.height / 2)
    
    // Set pages for demo
    setTotalPages(1)
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

    const rect = containerRef.current.getBoundingClientRect()
    const x = (e.clientX - rect.left) / scale
    const y = (e.clientY - rect.top) / scale

    const newField: SignatureField = {
      id: `field-${Date.now()}`,
      type: draggedFieldType as any,
      signer: selectedSigner,
      required: true,
      x,
      y,
      width: 200,
      height: 50,
      page: currentPage,
      label: `${draggedFieldType} field`
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

        {/* Field Types */}
        <div className="space-y-2 mb-4">
          <Label>Drag fields to document</Label>
          {FIELD_TYPES.map(fieldType => {
            const Icon = fieldType.icon
            return (
              <div
                key={fieldType.value}
                draggable
                onDragStart={(e) => handleDragStart(e, fieldType.value)}
                onDragEnd={handleDragEnd}
                className={cn(
                  "flex items-center gap-2 p-3 border rounded-md cursor-move",
                  "hover:bg-accent hover:border-accent-foreground/20",
                  "transition-colors",
                  isDragging && draggedFieldType === fieldType.value && "opacity-50"
                )}
              >
                <Icon className="h-4 w-4" />
                <span className="text-sm">{fieldType.label}</span>
                <IconGripVertical className="h-4 w-4 ml-auto text-muted-foreground" />
              </div>
            )
          })}
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
          className="relative overflow-auto flex-1 bg-gray-100"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          <div className="relative inline-block">
            <canvas 
              ref={canvasRef}
              className="bg-white shadow-lg"
            />
            
            {/* Render fields */}
            {fields.filter(f => f.page === currentPage).map(field => {
              const signer = signers.find(s => s.id === field.signer)
              const Icon = getFieldIcon(field.type)
              
              return (
                <div
                  key={field.id}
                  onClick={() => handleFieldClick(field.id)}
                  style={{
                    position: 'absolute',
                    left: field.x * scale,
                    top: field.y * scale,
                    width: field.width * scale,
                    height: field.height * scale,
                    border: `2px solid ${signer?.color || '#666'}`,
                    backgroundColor: `${signer?.color}20` || '#66666620',
                    cursor: 'move'
                  }}
                  className={cn(
                    "flex items-center justify-center gap-2 rounded",
                    "hover:ring-2 hover:ring-offset-1",
                    selectedField === field.id && "ring-2 ring-primary"
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
                      className="absolute bottom-0 right-0 w-4 h-4 bg-primary cursor-se-resize"
                      onMouseDown={(e) => {
                        e.stopPropagation()
                        // Handle resize
                      }}
                    >
                      <IconResize className="h-3 w-3 text-white" />
                    </div>
                  )}
                </div>
              )
            })}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}