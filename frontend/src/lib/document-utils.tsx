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
 * Now with colored icons matching the sidebar design
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
  
  // PDF files - Blue color for PDF documents
  if (type.includes('pdf') || extension === 'pdf') {
    return <IconFileTypePdf className={`${className} text-blue-600 dark:text-blue-400`} />
  }
  
  // Word documents - Blue color for text documents
  if (type.includes('word') || type.includes('officedocument') || 
      extension.includes('doc') || extension === 'docx') {
    return <IconFileText className={`${className} text-blue-600 dark:text-blue-400`} />
  }
  
  // Excel/Spreadsheets - Green color for spreadsheets
  if (type.includes('spreadsheet') || type.includes('excel') ||
      extension === 'xlsx' || extension === 'xls' || extension === 'csv') {
    return <IconFileText className={`${className} text-green-600 dark:text-green-400`} />
  }
  
  // PowerPoint - Orange color for presentations
  if (type.includes('presentation') || type.includes('powerpoint') ||
      extension === 'pptx' || extension === 'ppt') {
    return <IconFileText className={`${className} text-orange-600 dark:text-orange-400`} />
  }
  
  // Images - Purple color for visual files
  if (type.includes('image') || ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'].includes(extension)) {
    return <IconPhoto className={`${className} text-purple-600 dark:text-purple-400`} />
  }
  
  // Videos - Pink color for video files
  if (type.includes('video') || ['mp4', 'avi', 'mov', 'wmv', 'flv'].includes(extension)) {
    return <IconVideo className={`${className} text-pink-600 dark:text-pink-400`} />
  }
  
  // Audio - Yellow color for audio files
  if (type.includes('audio') || ['mp3', 'wav', 'flac', 'aac', 'ogg'].includes(extension)) {
    return <IconMusic className={`${className} text-yellow-600 dark:text-yellow-400`} />
  }
  
  // Text files - Indigo color for plain text
  if (type.includes('text') || ['txt', 'md', 'rtf'].includes(extension)) {
    return <IconFileText className={`${className} text-indigo-600 dark:text-indigo-400`} />
  }
  
  // Default file icon - Gray color for unknown types
  return <IconFile className={`${className} text-gray-600 dark:text-gray-400`} />
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
 * Returns user-friendly status label for document state
 */
export function getStatusLabel(status: string | number | null | undefined, t?: (key: string) => string): string {
  const statusKey = getStatusKey(status)
  
  // If translation function is provided, use it
  if (t) {
    return t(`documents.statusLabels.${statusKey}`)
  }
  
  // User-friendly labels (no technical jargon)
  const friendlyLabels: Record<string, string> = {
    'INDEXED': 'Disponible',           // Simple and positive
    'PROCESSING': 'Preparando...',     // Less technical, more friendly
    'INDEXING_ERROR': 'Revisar',       // Non-alarming, actionable
    'PENDING': 'En cola'               // Simple queue concept
  }
  
  return friendlyLabels[statusKey] || 'En cola'
}

/**
 * Returns user-friendly status description
 */
export function getStatusDescription(status: string | number | null | undefined, t?: (key: string) => string): string {
  const statusKey = getStatusKey(status)
  
  // If translation function is provided, use it
  if (t) {
    return t(`documents.statusDescriptions.${statusKey}`)
  }
  
  // User-friendly descriptions (focus on what user can do)
  const friendlyDescriptions: Record<string, string> = {
    'INDEXED': 'Listo para búsqueda y análisis',
    'PROCESSING': 'Analizando contenido del documento',
    'INDEXING_ERROR': 'Necesita ser reprocesado',
    'PENDING': 'Esperando turno para ser procesado'
  }
  
  return friendlyDescriptions[statusKey] || 'Esperando turno para ser procesado'
}

/**
 * Returns status color classes - more subtle and less alarming
 */
export function getStatusColor(indexed: string | number | null | undefined): string {
  // Get the normalized status key
  const statusKey = getStatusKey(indexed)
  
  switch (statusKey) {
    case 'INDEXED':
      return 'bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300'  // Professional blue instead of green
    case 'PROCESSING':
      return 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300'  // Softer amber
    case 'INDEXING_ERROR':
      return 'bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-300'  // Orange instead of alarming red
    case 'PENDING':
      return 'bg-slate-50 text-slate-600 dark:bg-slate-800/50 dark:text-slate-400'  // Subtle gray
    default:
      return 'bg-slate-50 text-slate-600 dark:bg-slate-800/50 dark:text-slate-400'
  }
}

/**
 * Returns whether document status should show as "ready to use" 
 */
export function isDocumentReady(indexed: string | number | null | undefined): boolean {
  const statusKey = getStatusKey(indexed)
  return statusKey === 'INDEXED'
}

/**
 * Returns whether document is currently being processed
 */
export function isDocumentProcessing(indexed: string | number | null | undefined): boolean {
  const statusKey = getStatusKey(indexed)
  return statusKey === 'PROCESSING'
}

/**
 * Returns whether document needs user attention
 */
export function needsAttention(indexed: string | number | null | undefined): boolean {
  const statusKey = getStatusKey(indexed)
  return statusKey === 'INDEXING_ERROR'
}

/**
 * Returns user-friendly status badge variant for UI components
 */
export function getStatusVariant(indexed: string | number | null | undefined): 'default' | 'secondary' | 'outline' | 'destructive' {
  const statusKey = getStatusKey(indexed)
  
  switch (statusKey) {
    case 'INDEXED':
      return 'default'      // Normal blue badge - "ready"
    case 'PROCESSING':
      return 'secondary'    // Muted badge for processing
    case 'INDEXING_ERROR':
      return 'outline'      // Outline badge - less alarming than destructive
    case 'PENDING':
      return 'secondary'    // Muted badge for pending
    default:
      return 'secondary'
  }
}

/**
 * Returns status icon component for different states
 */
export function getStatusIcon(indexed: string | number | null | undefined) {
  const statusKey = getStatusKey(indexed)
  
  // Import icons lazily to avoid bundle issues
  const icons = {
    'INDEXED': () => import('@tabler/icons-react').then(m => m.IconCheck),
    'PROCESSING': () => import('@tabler/icons-react').then(m => m.IconLoader2),
    'INDEXING_ERROR': () => import('@tabler/icons-react').then(m => m.IconAlertCircle),
    'PENDING': () => import('@tabler/icons-react').then(m => m.IconClock)
  }
  
  return icons[statusKey] || icons['PENDING']
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

/**
 * Checks if a file is an image
 */
export function isImageFile(fileType: string | undefined | null, mimeType?: string | undefined | null, filename?: string): boolean {
  const type = (fileType || '').toLowerCase()
  const mime = (mimeType || '').toLowerCase()
  const extension = getFileExtension(filename || '')
  
  // Check by MIME type (most reliable)
  if (mime.startsWith('image/')) {
    return true
  }
  
  // Check by file type
  if (type.includes('image')) {
    return true
  }
  
  // Check by extension
  const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'bmp', 'tiff', 'tif', 'ico']
  return imageExtensions.includes(extension)
}

/**
 * Gets the image format from MIME type or filename
 */
export function getImageFormat(mimeType?: string | undefined | null, filename?: string): string {
  if (mimeType && mimeType.startsWith('image/')) {
    return mimeType.split('/')[1]?.toUpperCase() || 'IMAGE'
  }
  
  const extension = getFileExtension(filename || '')
  return extension.toUpperCase() || 'IMAGE'
}