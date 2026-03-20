/**
 * Document Utilities for Emma On-Premise
 *
 * File icons, size formatting, status badges, and date formatting
 * for the synchronized documents table.
 */

import {
  IconFile,
  IconFileText,
  IconFileTypePdf,
  IconFileTypeDocx,
  IconPhoto,
  IconVideo,
  IconMusic
} from '@tabler/icons-react'

// ─── File Icons ───────────────────────────────────────────────────────────────

const sizeClasses = {
  sm: 'h-4 w-4',
  md: 'h-5 w-5',
  lg: 'h-6 w-6'
}

/**
 * Returns a colored icon based on MIME type or file extension.
 */
export function getFileIcon(
  mimeType: string | null | undefined,
  fileExtension: string | null | undefined,
  size: 'sm' | 'md' | 'lg' = 'md'
) {
  const type = (mimeType || '').toLowerCase()
  const ext = (fileExtension || '').toLowerCase().replace('.', '')
  const className = sizeClasses[size]

  // PDF
  if (type.includes('pdf') || ext === 'pdf') {
    return <IconFileTypePdf className={`${className} text-blue-600 dark:text-blue-400`} />
  }

  // Word
  if (type.includes('word') || type.includes('officedocument.wordprocessing') ||
      ext === 'doc' || ext === 'docx') {
    return <IconFileTypeDocx className={`${className} text-blue-600 dark:text-blue-400`} />
  }

  // ODT
  if (type.includes('opendocument.text') || ext === 'odt') {
    return <IconFileTypeDocx className={`${className} text-cyan-600 dark:text-cyan-400`} />
  }

  // Excel / Spreadsheets
  if (type.includes('spreadsheet') || type.includes('excel') ||
      ext === 'xlsx' || ext === 'xls' || ext === 'csv') {
    return <IconFileText className={`${className} text-green-600 dark:text-green-400`} />
  }

  // ODS
  if (type.includes('opendocument.spreadsheet') || ext === 'ods') {
    return <IconFileText className={`${className} text-teal-600 dark:text-teal-400`} />
  }

  // PowerPoint
  if (type.includes('presentation') || type.includes('powerpoint') ||
      ext === 'pptx' || ext === 'ppt') {
    return <IconFileText className={`${className} text-orange-600 dark:text-orange-400`} />
  }

  // ODP
  if (type.includes('opendocument.presentation') || ext === 'odp') {
    return <IconFileText className={`${className} text-amber-600 dark:text-amber-400`} />
  }

  // Images
  if (type.includes('image') || ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'].includes(ext)) {
    return <IconPhoto className={`${className} text-purple-600 dark:text-purple-400`} />
  }

  // Video
  if (type.includes('video') || ['mp4', 'avi', 'mov', 'wmv', 'flv'].includes(ext)) {
    return <IconVideo className={`${className} text-pink-600 dark:text-pink-400`} />
  }

  // Audio
  if (type.includes('audio') || ['mp3', 'wav', 'flac', 'aac', 'ogg'].includes(ext)) {
    return <IconMusic className={`${className} text-yellow-600 dark:text-yellow-400`} />
  }

  // Text
  if (type.includes('text') || ['txt', 'md', 'rtf'].includes(ext)) {
    return <IconFileText className={`${className} text-indigo-600 dark:text-indigo-400`} />
  }

  // Default
  return <IconFile className={`${className} text-gray-600 dark:text-gray-400`} />
}

// ─── File Size ────────────────────────────────────────────────────────────────

export function formatFileSize(bytes: number | null | undefined): string {
  if (!bytes || bytes === 0) return '—'

  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// ─── Status Badges ────────────────────────────────────────────────────────────

interface StatusBadgeConfig {
  label: string
  variant: 'default' | 'secondary' | 'destructive' | 'outline'
}

/**
 * Maps on-premise indexing_status strings to Spanish labels and Badge variants.
 */
export function getStatusBadgeConfig(status: string | null | undefined): StatusBadgeConfig {
  const s = (status || '').toLowerCase()

  switch (s) {
    case 'indexed':
      return { label: 'Indexado', variant: 'default' }
    case 'processing':
      return { label: 'Procesando', variant: 'secondary' }
    case 'pending':
      return { label: 'Pendiente', variant: 'outline' }
    case 'failed':
      return { label: 'Error', variant: 'destructive' }
    default:
      return { label: status || 'Desconocido', variant: 'outline' }
  }
}

// ─── Date Formatting ──────────────────────────────────────────────────────────

export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '—'

  const date = new Date(dateString)
  if (isNaN(date.getTime())) return '—'

  return date.toLocaleDateString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}
