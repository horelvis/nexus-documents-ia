"use client"

import React, { useState, useCallback, useEffect } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useDropzone } from "react-dropzone"
import { UploadDocumentSchema } from "@/lib/types"
import { useDocumentService } from "@/lib/services/document.service"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { 
  IconCloudUpload, 
  IconFile, 
  IconX, 
  IconCheck,
  IconLoader2,
  IconMinus,
  IconMaximize
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle 
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"

interface UploadFile {
  file: File
  id: string
  progress: number
  status: 'pending' | 'uploading' | 'success' | 'error'
  error?: string
}

interface UploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onUploadComplete?: (files: UploadFile[]) => void
}

export function UploadDialog({ open, onOpenChange, onUploadComplete }: UploadDialogProps) {
  const [files, setFiles] = useState<UploadFile[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [isMinimized, setIsMinimized] = useState(false)
  const [uploadCompleted, setUploadCompleted] = useState(false)
  const documentService = useDocumentService()

  const form = useForm<z.infer<typeof UploadDocumentSchema>>({
    mode: 'onChange',
    resolver: zodResolver(UploadDocumentSchema),
    defaultValues: {
      category: '',
      tags: '',
      description: '',
      files: [],
    },
  })

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const newFiles: UploadFile[] = acceptedFiles.map(file => ({
      file,
      id: Math.random().toString(36).substr(2, 9),
      progress: 0,
      status: 'pending'
    }))
    
    setFiles(prev => {
      const updatedFiles = [...prev, ...newFiles]
      // Update form with new files
      form.setValue('files', updatedFiles.map(f => f.file))
      return updatedFiles
    })
  }, [form])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/plain': ['.txt'],
      'image/*': ['.png', '.jpg', '.jpeg', '.gif'],
    },
    maxSize: 50 * 1024 * 1024, // 50MB
    multiple: true,
    onDragEnter: () => {},
    onDragOver: () => {},
    onDragLeave: () => {},
  })

  const removeFile = (id: string) => {
    setFiles((prev: UploadFile[]) => {
      const updatedFiles = prev.filter((file: UploadFile) => file.id !== id)
      form.setValue('files', updatedFiles.map(f => f.file))
      return updatedFiles
    })
  }

  const handleSubmit = async (values: z.infer<typeof UploadDocumentSchema>) => {
    setIsUploading(true)
    const pendingFiles = files.filter((f: UploadFile) => f.status === 'pending')
    
    // Auto-minimize during upload if there are many files
    if (pendingFiles.length > 3) {
      setIsMinimized(true)
    }

    try {
      // Mark all files as uploading
      setFiles((prev: UploadFile[]) => prev.map((f: UploadFile) => 
        f.status === 'pending' ? { ...f, status: 'uploading' as const, progress: 0 } : f
      ))

      // Simulate progress for UX
      const progressInterval = setInterval(() => {
        setFiles((prev: UploadFile[]) => prev.map((f: UploadFile) => 
          f.status === 'uploading' && f.progress < 90 ? { ...f, progress: f.progress + 10 } : f
        ))
      }, 300)

      // Upload to backend
      const response = await documentService.uploadDocuments({
        files: pendingFiles.map(f => f.file),
        category: values.category,
        tags: values.tags,
        description: values.description,
      })

      clearInterval(progressInterval)

      if (response.error) {
        // Mark all uploading files as error
        setFiles((prev: UploadFile[]) => prev.map((f: UploadFile) => 
          f.status === 'uploading' ? { 
            ...f, 
            status: 'error' as const, 
            error: response.error || 'Upload failed'
          } : f
        ))
      } else {
        // Mark all uploading files as success
        setFiles((prev: UploadFile[]) => prev.map((f: UploadFile) => 
          f.status === 'uploading' ? { 
            ...f, 
            status: 'success' as const, 
            progress: 100 
          } : f
        ))
        setUploadCompleted(true)
      }
    } catch (error) {
      // Mark all uploading files as error
      setFiles((prev: UploadFile[]) => prev.map((f: UploadFile) => 
        f.status === 'uploading' ? { 
          ...f, 
          status: 'error' as const, 
          error: error instanceof Error ? error.message : 'Upload failed'
        } : f
      ))
    } finally {
      setIsUploading(false)
    }
  }

  // Handle upload completion in useEffect to avoid setState during render
  useEffect(() => {
    if (uploadCompleted && !isUploading) {
      const successFiles = files.filter((f: UploadFile) => f.status === 'success')
      if (successFiles.length > 0 && onUploadComplete) {
        try {
          onUploadComplete(successFiles)
        } catch (error) {
          console.error('Error calling onUploadComplete:', error)
        }
      }
      setUploadCompleted(false)
    }
  }, [uploadCompleted, isUploading, files, onUploadComplete])

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const getStatusIcon = (status: UploadFile['status']) => {
    switch (status) {
      case 'pending':
        return <IconFile className="h-4 w-4 text-gray-500" />
      case 'uploading':
        return <IconLoader2 className="h-4 w-4 text-blue-500 animate-spin" />
      case 'success':
        return <IconCheck className="h-4 w-4 text-green-500" />
      case 'error':
        return <IconX className="h-4 w-4 text-red-500" />
    }
  }

  const totalProgress = files.length > 0 
    ? files.reduce((acc: number, file: UploadFile) => acc + file.progress, 0) / files.length 
    : 0

  const completedFiles = files.filter((f: UploadFile) => f.status === 'success').length
  const errorFiles = files.filter((f: UploadFile) => f.status === 'error').length
  const uploadingFiles = files.filter((f: UploadFile) => f.status === 'uploading').length

  // Reset form when dialog closes
  useEffect(() => {
    if (!open) {
      form.reset()
      setFiles([])
      setIsMinimized(false)
      setUploadCompleted(false)
    }
  }, [open, form])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent 
        className={`transition-all duration-300 ${
          isMinimized 
            ? 'max-w-sm h-auto' 
            : 'max-w-4xl max-h-[90vh] overflow-y-auto'
        }`}
      >
        <DialogHeader className="flex flex-row items-center justify-between">
          <DialogTitle className="flex items-center gap-2">
            <IconCloudUpload className="h-5 w-5" />
            Upload Documents
            {files.length > 0 && (
              <Badge variant="secondary">
                {files.length} file{files.length > 1 ? 's' : ''}
              </Badge>
            )}
          </DialogTitle>
          <div className={'flex flex items-center gap-2'}>
            {isUploading && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsMinimized(!isMinimized)}
              >
                {isMinimized ? (
                  <IconMaximize className="h-4 w-4" />
                ) : (
                  <IconMinus className="h-4 w-4" />
                )}
              </Button>
            )}
          </div>
        </DialogHeader>

        {/* Minimized View */}
        {isMinimized ? (
          <div className="py-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">
                Uploading {uploadingFiles} of {files.length} files...
              </span>
              <span className="text-sm text-muted-foreground">
                {Math.round(totalProgress)}%
              </span>
            </div>
            <Progress value={totalProgress} className="mb-2" />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{completedFiles} completed</span>
              {errorFiles > 0 && <span className="text-red-500">{errorFiles} errors</span>}
            </div>
            {!isUploading && completedFiles > 0 && (
              <div className="mt-3 p-2 bg-green-50 rounded-md">
                <div className="flex items-center gap-2">
                  <IconCheck className="h-4 w-4 text-green-600" />
                  <span className="text-sm text-green-800">
                    {completedFiles} file{completedFiles > 1 ? 's' : ''} uploaded successfully!
                  </span>
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Full View */
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
              {/* Upload Zone */}
              <div
                {...getRootProps()}
                className={`
                  border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors
                  ${isDragActive 
                    ? 'border-primary bg-primary/5' 
                    : 'border-muted-foreground/25 hover:border-muted-foreground/50'
                  }
                `}
              >
                <input {...getInputProps()} />
                <IconCloudUpload className="mx-auto h-10 w-10 text-muted-foreground mb-3" />
                {isDragActive ? (
                  <p className="text-base">Drop the files here...</p>
                ) : (
                  <div>
                    <p className="text-base mb-1">Drag & drop files here, or click to select</p>
                    <p className="text-sm text-muted-foreground">
                      Max 50MB • PDF, DOC, DOCX, TXT, Images
                    </p>
                  </div>
                )}
              </div>

              {/* Upload Settings */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Upload Settings</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <FormField
                      disabled={isUploading}
                      control={form.control}
                      name="category"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="text-sm font-medium">Category</FormLabel>
                          <FormControl>
                            <Input 
                              {...field}
                              placeholder="e.g., Contracts, Reports"
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      disabled={isUploading}
                      control={form.control}
                      name="tags"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="text-sm font-medium">Tags</FormLabel>
                          <FormControl>
                            <Input 
                              {...field}
                              placeholder="important, draft, review"
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                  <FormField
                    disabled={isUploading}
                    control={form.control}
                    name="description"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel className="text-sm font-medium">Description (Optional)</FormLabel>
                        <FormControl>
                          <Input 
                            {...field}
                            placeholder="Brief description"
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

              {/* File List */}
              {files.length > 0 && (
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between">
                    <CardTitle>Files ({files.length})</CardTitle>
                    <Button 
                      type="submit"
                      disabled={isUploading || files.every((f: UploadFile) => f.status !== 'pending')}
                    >
                      {isUploading ? (
                        <>
                          <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                          Uploading...
                        </>
                      ) : (
                        <>
                          <IconCloudUpload className="mr-2 h-4 w-4" />
                          Upload All
                        </>
                      )}
                    </Button>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3 max-h-64 overflow-y-auto">
                      {files.map((uploadFile: UploadFile) => (
                        <div key={uploadFile.id} className="flex items-center gap-3 p-3 border rounded-lg">
                          <div className="flex-shrink-0">
                            {getStatusIcon(uploadFile.status)}
                          </div>
                          
                          <div className="flex-grow min-w-0">
                            <div className="flex items-center justify-between mb-1">
                              <p className="text-sm font-medium truncate">{uploadFile.file.name}</p>
                              <p className="text-sm text-muted-foreground">{formatFileSize(uploadFile.file.size)}</p>
                            </div>
                            
                            {uploadFile.status === 'uploading' && (
                              <Progress value={uploadFile.progress} className="h-1" />
                            )}
                            
                            {uploadFile.status === 'error' && uploadFile.error && (
                              <p className="text-sm text-red-500">{uploadFile.error}</p>
                            )}
                            
                            {uploadFile.status === 'success' && (
                              <p className="text-sm text-green-600">Upload completed</p>
                            )}
                          </div>
                          
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => removeFile(uploadFile.id)}
                            disabled={uploadFile.status === 'uploading'}
                          >
                            <IconX className="h-4 w-4" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </form>
          </Form>
        )}
      </DialogContent>
    </Dialog>
  )
}