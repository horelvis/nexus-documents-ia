// frontend/app/components/upload/document-upload.tsx
import { useState, useRef } from 'react'
import { useFetcher } from '@remix-run/react'
import { Upload, File, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import { uploadValidation } from '#app/services/upload-api.server'
import { Button } from '#app/components/ui/button'
import { Card, CardContent } from '#app/components/ui/card'
import { Badge } from '#app/components/ui/badge'
import { Progress } from '#app/components/ui/progress'

interface DocumentUploadProps {
  onUploadComplete?: (document: any) => void
  onUploadError?: (error: string) => void
  maxFiles?: number
  allowedTypes?: string[]
  className?: string
}

interface UploadingFile {
  file: File
  id: string
  progress: number
  status: 'uploading' | 'processing' | 'completed' | 'error'
  error?: string
  result?: any
}

export function DocumentUpload({
  onUploadComplete,
  onUploadError,
  maxFiles = 5,
  allowedTypes = uploadValidation.documentTypes,
  className = ""
}: DocumentUploadProps) {
  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([])
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const uploadFetcher = useFetcher()

  const handleFileSelect = (files: FileList | null) => {
    if (!files) return

    const fileArray = Array.from(files)
    
    // Validar número máximo de archivos
    if (uploadingFiles.length + fileArray.length > maxFiles) {
      onUploadError?.(`Máximo ${maxFiles} archivos permitidos`)
      return
    }

    // Procesar cada archivo
    fileArray.forEach(file => {
      // Validar archivo
      const validation = uploadValidation.validateDocument(file)
      if (!validation.isValid) {
        onUploadError?.(validation.error!)
        return
      }

      // Crear entrada de upload
      const uploadId = crypto.randomUUID()
      const uploadingFile: UploadingFile = {
        file,
        id: uploadId,
        progress: 0,
        status: 'uploading'
      }

      setUploadingFiles(prev => [...prev, uploadingFile])

      // Crear FormData y enviar
      const formData = new FormData()
      formData.append('file', file)
      formData.append('upload_id', uploadId)

      // Enviar con Remix fetcher
      uploadFetcher.submit(formData, {
        method: 'POST',
        action: '/api/upload/document',
        encType: 'multipart/form-data'
      })
    })

    // Limpiar input
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  // Manejar respuesta del upload
  React.useEffect(() => {
    if (uploadFetcher.data) {
      const response = uploadFetcher.data

      if (response.success) {
        // Actualizar estado del archivo
        setUploadingFiles(prev =>
          prev.map(f =>
            f.id === response.upload_id
              ? { ...f, status: 'completed', progress: 100, result: response.document }
              : f
          )
        )
        onUploadComplete?.(response.document)
      } else {
        // Manejar error
        setUploadingFiles(prev =>
          prev.map(f =>
            f.id === response.upload_id
              ? { ...f, status: 'error', error: response.error }
              : f
          )
        )
        onUploadError?.(response.error)
      }
    }
  }, [uploadFetcher.data, onUploadComplete, onUploadError])

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    handleFileSelect(e.dataTransfer.files)
  }

  const removeFile = (id: string) => {
    setUploadingFiles(prev => prev.filter(f => f.id !== id))
  }

  const retryUpload = (file: UploadingFile) => {
    setUploadingFiles(prev =>
      prev.map(f =>
        f.id === file.id
          ? { ...f, status: 'uploading', progress: 0, error: undefined }
          : f
      )
    )

    const formData = new FormData()
    formData.append('file', file.file)
    formData.append('upload_id', file.id)

    uploadFetcher.submit(formData, {
      method: 'POST',
      action: '/api/upload/document',
      encType: 'multipart/form-data'
    })
  }

  const getStatusIcon = (status: UploadingFile['status']) => {
    switch (status) {
      case 'uploading':
      case 'processing':
        return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'error':
        return <AlertCircle className="h-4 w-4 text-red-500" />
    }
  }

  const getStatusText = (file: UploadingFile) => {
    switch (file.status) {
      case 'uploading':
        return 'Subiendo...'
      case 'processing':
        return 'Procesando...'
      case 'completed':
        return 'Completado'
      case 'error':
        return file.error || 'Error'
    }
  }

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Drop Zone */}
      <Card 
        className={`border-2 border-dashed transition-colors cursor-pointer ${
          dragOver 
            ? 'border-primary bg-primary/5' 
            : 'border-muted-foreground/25 hover:border-primary/50'
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <CardContent className="flex flex-col items-center justify-center py-8 text-center">
          <Upload className="h-8 w-8 text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium mb-2">
            Subir Documentos
          </h3>
          <p className="text-sm text-muted-foreground mb-4">
            Arrastra archivos aquí o haz clic para seleccionar
          </p>
          <div className="flex flex-wrap gap-2 justify-center">
            <Badge variant="secondary">PDF</Badge>
            <Badge variant="secondary">Word</Badge>
            <Badge variant="secondary">Excel</Badge>
            <Badge variant="secondary">PowerPoint</Badge>
            <Badge variant="secondary">Texto</Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Máximo {maxFiles} archivos, hasta 50MB cada uno
          </p>
        </CardContent>
      </Card>

      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={allowedTypes.join(',')}
        className="hidden"
        onChange={(e) => handleFileSelect(e.target.files)}
      />

      {/* Uploading Files */}
      {uploadingFiles.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium">Archivos subiendo</h4>
          {uploadingFiles.map((file) => (
            <Card key={file.id} className="p-3">
              <div className="flex items-center gap-3">
                <File className="h-8 w-8 text-blue-500 flex-shrink-0" />
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-sm font-medium truncate">
                      {file.file.name}
                    </p>
                    <div className="flex items-center gap-2">
                      {getStatusIcon(file.status)}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeFile(file.id)}
                        className="h-6 w-6 p-0"
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                  
                  <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
                    <span>{uploadValidation.formatFileSize(file.file.size)}</span>
                    <span>{getStatusText(file)}</span>
                  </div>
                  
                  {file.status === 'uploading' && (
                    <Progress value={file.progress} className="h-1" />
                  )}
                  
                  {file.status === 'error' && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => retryUpload(file)}
                      className="mt-2"
                    >
                      Reintentar
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}