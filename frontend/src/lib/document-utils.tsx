import { 
  IconFile, 
  IconFileText, 
  IconFileTypePdf,
  IconPhoto,
  IconVideo,
  IconMusic
} from "@tabler/icons-react"

export interface FileIconProps {
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

const sizeClasses = {
  sm: 'h-4 w-4',
  md: 'h-5 w-5', 
  lg: 'h-6 w-6'
}

/**
 * Returns the appropriate file icon based on file type, MIME type, or filename extension
 */
export function getFileIcon(
  fileType: string | undefined | null, 
  mimeType?: string | undefined | null, 
  filename?: string,
  size: 'sm' | 'md' | 'lg' = 'md'
) {
  // Try to determine file type from multiple sources
  const type = (fileType || mimeType || '').toLowerCase()
  const extension = filename ? filename.split('.').pop()?.toLowerCase() || '' : ''
  
  const className = sizeClasses[size]
  
  // PDF files
  if (type.includes('pdf') || extension === 'pdf') {
    return <IconFileTypePdf className={`${className} text-muted-foreground`} />
  }
  
  // Word documents
  if (type.includes('word') || type.includes('officedocument') || 
      extension.includes('doc') || extension === 'docx') {
    return <IconFileText className={`${className} text-muted-foreground`} />
  }
  
  // Excel/Spreadsheets
  if (type.includes('spreadsheet') || type.includes('excel') ||
      extension === 'xlsx' || extension === 'xls' || extension === 'csv') {
    return <IconFileText className={`${className} text-muted-foreground`} />
  }
  
  // PowerPoint
  if (type.includes('presentation') || type.includes('powerpoint') ||
      extension === 'pptx' || extension === 'ppt') {
    return <IconFileText className={`${className} text-muted-foreground`} />
  }
  
  // Images
  if (type.includes('image') || ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'].includes(extension)) {
    return <IconPhoto className={`${className} text-muted-foreground`} />
  }
  
  // Videos
  if (type.includes('video') || ['mp4', 'avi', 'mov', 'wmv', 'flv'].includes(extension)) {
    return <IconVideo className={`${className} text-muted-foreground`} />
  }
  
  // Audio
  if (type.includes('audio') || ['mp3', 'wav', 'flac', 'aac', 'ogg'].includes(extension)) {
    return <IconMusic className={`${className} text-muted-foreground`} />
  }
  
  // Text files
  if (type.includes('text') || ['txt', 'md', 'rtf'].includes(extension)) {
    return <IconFileText className={`${className} text-muted-foreground`} />
  }
  
  // Default file icon
  return <IconFile className={`${className} text-muted-foreground`} />
}

/**
 * Formats file size in human readable format
 */
export function formatFileSize(bytes: number | null | undefined): string {
  if (!bytes || bytes === 0) return '0 Bytes'
  
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

/**
 * Maps numeric or string status values to descriptive status keys
 */
export function getStatusKey(status: string | number | null | undefined): string {
  // Map numeric status values to string constants
  const statusMap: Record<string | number, string> = {
    '1': 'INDEXED',
    '2': 'PROCESSING', 
    '3': 'INDEXING_ERROR',
    '0': 'PENDING',
    1: 'INDEXED',
    2: 'PROCESSING',
    3: 'INDEXING_ERROR',
    0: 'PENDING',
    // String versions remain as is
    'INDEXED': 'INDEXED',
    'PROCESSING': 'PROCESSING',
    'INDEXING_ERROR': 'INDEXING_ERROR',
    'PENDING': 'PENDING'
  }
  
  // Return mapped value or default
  if (status === null || status === undefined) return 'PENDING'
  return statusMap[status] || 'PENDING'
}

/**
 * Returns translated status label (requires translation context)
 */
export function getStatusLabel(status: string | number | null | undefined, t?: (key: string) => string): string {
  const statusKey = getStatusKey(status)
  
  // If translation function is provided, use it
  if (t) {
    return t(`documents.statusLabels.${statusKey}`)
  }
  
  // Fallback to Spanish hardcoded values
  const fallbackMap: Record<string, string> = {
    'INDEXED': 'Procesado correctamente',
    'PROCESSING': 'Procesando contenido',
    'INDEXING_ERROR': 'Error en el procesamiento',
    'PENDING': 'Pendiente de procesar'
  }
  
  return fallbackMap[statusKey] || statusKey
}

/**
 * Returns detailed status description (requires translation context)
 */
export function getStatusDescription(status: string | number | null | undefined, t?: (key: string) => string): string {
  const statusKey = getStatusKey(status)
  
  // If translation function is provided, use it
  if (t) {
    return t(`documents.statusDescriptions.${statusKey}`)
  }
  
  // Fallback to Spanish hardcoded descriptions
  const fallbackMap: Record<string, string> = {
    'INDEXED': 'El documento ha sido procesado y está disponible para búsqueda',
    'PROCESSING': 'El documento se está analizando y extrayendo su contenido',
    'INDEXING_ERROR': 'Hubo un problema al procesar el documento. Puede reintentarse',
    'PENDING': 'El documento está en cola esperando a ser procesado'
  }
  
  return fallbackMap[statusKey] || statusKey
}

/**
 * Returns status color classes based on indexing status
 */
export function getStatusColor(indexed: string | number | null | undefined): string {
  // Get the normalized status key
  const statusKey = getStatusKey(indexed)
  
  switch (statusKey) {
    case 'INDEXED':
      return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300'
    case 'PROCESSING':
      return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300'
    case 'INDEXING_ERROR':
      return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300'
    case 'PENDING':
      return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300'
    default:
      return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300'
  }
}

/**
 * Returns relative time string from date
 */
export function getRelativeTime(dateString: string | null | undefined): string {
  if (!dateString) return 'Unknown date'
  
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return 'Invalid date'
  
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMinutes = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMinutes / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMinutes < 1) return 'Just now'
  if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes > 1 ? 's' : ''} ago`
  if (diffHours < 1) return 'Less than an hour ago'
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} week${Math.floor(diffDays / 7) > 1 ? 's' : ''} ago`
  
  return date.toLocaleDateString()
}

/**
 * Extracts file extension from filename
 */
export function getFileExtension(filename: string): string {
  return filename.split('.').pop()?.toLowerCase() || ''
}

/**
 * Checks if a file type is supported for preview
 */
export function isPreviewSupported(fileType: string | undefined | null, filename?: string): boolean {
  const type = (fileType || '').toLowerCase()
  const extension = getFileExtension(filename || '')
  
  // Text-based files that can be previewed
  const previewableTypes = ['text', 'json', 'xml', 'html', 'css', 'javascript']
  const previewableExtensions = ['txt', 'md', 'json', 'xml', 'html', 'css', 'js', 'ts', 'csv']
  
  return previewableTypes.some(t => type.includes(t)) || 
         previewableExtensions.includes(extension)
}