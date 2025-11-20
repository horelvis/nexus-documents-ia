"use client"

import React, { useState, useCallback, useEffect } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useDropzone } from "react-dropzone"
import { UploadDocumentSchema } from "@/lib/types"
import { useDocumentService } from "@/lib/services/document.service"
import { NexusDocumentLoader } from "@/components/ui/nexus-loader"
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
  const [showSuccess, setShowSuccess] = useState(false)
  const [currentUploadIndex, setCurrentUploadIndex] = useState(0)
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

  const onDrop = (acceptedFiles: File[]) => {
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
  }

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/plain': ['.txt'],
      'application/vnd.oasis.opendocument.text': ['.odt'],
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
    setCurrentUploadIndex(0)
    const pendingFiles = files.filter((f: UploadFile) => f.status === 'pending')
    
    // Auto-minimize during upload if there are many files
    if (pendingFiles.length > 3) {
      setIsMinimized(true)
    }

    try {
      // Upload files one by one
      for (let index = 0; index < pendingFiles.length; index++) {
        const fileObj = pendingFiles[index]
        setCurrentUploadIndex(index + 1)
        // Mark current file as uploading with initial progress
        setFiles((prev: UploadFile[]) => prev.map((f: UploadFile) => 
          f.id === fileObj.id ? { ...f, status: 'uploading' as const, progress: 0 } : f
        ))

        try {
          // Upload single file with progress tracking
          const response = await documentService.uploadSingleDocument(
            fileObj.file,
            {
              category: values.category,
              tags: values.tags,
              description: values.description,
            },
            (progress: number) => {
              // Update progress for this specific file
              setFiles((prev: UploadFile[]) => prev.map((f: UploadFile) => 
                f.id === fileObj.id ? { ...f, progress } : f
              ))
            }
          )

          if (response.error) {
            // Mark this file as error
            let errorMessage = 'Upload failed'
            if (typeof response.error === 'string') {
              errorMessage = response.error
            } else if (response.error && typeof response.error === 'object' && response.error.message) {
              errorMessage = response.error.message
            }
            
            setFiles((prev: UploadFile[]) => prev.map((f: UploadFile) => 
              f.id === fileObj.id ? { 
                ...f, 
                status: 'error' as const, 
                error: errorMessage
              } : f
            ))
          } else {
            // Mark this file as success
            setFiles((prev: UploadFile[]) => prev.map((f: UploadFile) => 
              f.id === fileObj.id ? { 
                ...f, 
                status: 'success' as const, 
                progress: 100 
              } : f
            ))
          }

          // Small delay between uploads to avoid rate limiting (100ms)
          if (pendingFiles.indexOf(fileObj) < pendingFiles.length - 1) {
            await new Promise(resolve => setTimeout(resolve, 100))
          }

        } catch (error) {
          // Mark this file as error
          setFiles((prev: UploadFile[]) => prev.map((f: UploadFile) => 
            f.id === fileObj.id ? { 
              ...f, 
              status: 'error' as const, 
              error: error instanceof Error ? error.message : 'Upload failed'
            } : f
          ))
        }
      }
      // Logic for completion moved to useEffect
    } catch (error) {
      console.error('Upload error:', error)
    } finally {
      setIsUploading(false)
      setCurrentUploadIndex(0)
    }
  }

  // Effect to detect when all uploads are finished
  useEffect(() => {
    if (files.length === 0) return

    const pendingCount = files.filter(f => f.status === 'pending' || f.status === 'uploading').length
    const successCount = files.filter(f => f.status === 'success').length
    const errorCount = files.filter(f => f.status === 'error').length
    const total = files.length

    console.log('[DEBUG] UploadDialog Monitoring:', { 
        total, 
        pending: pendingCount, 
        success: successCount, 
        error: errorCount,
        isUploading,
        uploadCompleted 
    })

    // If nothing is pending or uploading, and we have at least one finished file (success or error)
    if (pendingCount === 0 && (successCount + errorCount === total) && total > 0) {
       // Only trigger once if we haven't marked it as completed yet
       if (!uploadCompleted && !isUploading) {
          console.log('[DEBUG] UploadDialog: All files processed. Setting uploadCompleted=true')
          
          if (successCount > 0) {
             setUploadCompleted(true)
             setShowSuccess(true)
          }
       } else {
           console.log('[DEBUG] UploadDialog: completion ignored (already completed or uploading flag stuck)', { uploadCompleted, isUploading })
       }
    }
  }, [files, isUploading, uploadCompleted])

  // Handle upload completion notification to parent
  useEffect(() => {
    if (uploadCompleted) {
      console.log('[DEBUG] UploadDialog: notifying parent of completion')
      const successFiles = files.filter((f: UploadFile) => f.status === 'success')
      
      if (successFiles.length > 0 && onUploadComplete) {
        try {
          onUploadComplete(successFiles)
          setUploadCompleted(false) // Reset internal state after notifying parent
        } catch (error) {
          console.error('Error calling onUploadComplete:', error)
        }
      }
    }
  }, [uploadCompleted, files, onUploadComplete])

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
  const totalFiles = files.length

  // Reset form when dialog closes
  useEffect(() => {
    if (!open) {
      form.reset()
      setFiles([])
      setIsMinimized(false)
      setUploadCompleted(false)
      setShowSuccess(false)
      setCurrentUploadIndex(0)
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

        {/* Success Message Overlay */}
        {showSuccess && !isMinimized && (
          <div className="absolute inset-0 bg-white/95 dark:bg-gray-900/95 z-10 flex items-center justify-center rounded-lg">
            <div className="text-center space-y-4 p-6">
              <div className="mx-auto w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center">
                <IconCheck className="h-8 w-8 text-green-600 dark:text-green-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-green-600 dark:text-green-400">
                  Upload Successful!
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                  {completedFiles} {completedFiles === 1 ? 'document has' : 'documents have'} been uploaded successfully.
                </p>
              </div>
              <p className="text-xs text-muted-foreground">
                Closing automatically...
              </p>
            </div>
          </div>
        )}

        {/* Minimized View */}
        {isMinimized ? (
          <div className="py-4">
            {isUploading ? (
              <NexusDocumentLoader
                action={`Subiendo ${currentUploadIndex} de ${totalFiles} archivos...`}
                progress={totalProgress}
              />
            ) : (
              <>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">
                    {`Upload complete: ${completedFiles} of ${totalFiles} files`}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    100%
                  </span>
                </div>
                <Progress value={100} className="mb-2" />
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{completedFiles} completed</span>
                  {errorFiles > 0 && <span className="text-red-500">{errorFiles} errors</span>}
                </div>
                {completedFiles > 0 && (
                  <div className="mt-3 p-2 bg-green-50 dark:bg-green-950 rounded-md">
                    <div className="flex items-center gap-2">
                      <IconCheck className="h-4 w-4 text-green-600 dark:text-green-400" />
                      <span className="text-sm text-green-800 dark:text-green-200">
                        {completedFiles} archivo{completedFiles > 1 ? 's' : ''} subido{completedFiles > 1 ? 's' : ''} correctamente!
                      </span>
                    </div>
                  </div>
                )}
              </>
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
