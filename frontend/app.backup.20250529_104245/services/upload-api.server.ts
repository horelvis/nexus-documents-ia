// frontend/app/services/upload-api.server.ts
import type { LoaderFunctionArgs } from '@remix-run/node'
import { ApiService } from '#app/services/api.server'

export interface UploadApiService {
  uploadDocument(formData: FormData): Promise<DocumentUploadResponse>
  uploadImage(formData: FormData): Promise<ImageUploadResponse>
  getUploadStatus(uploadId: string): Promise<UploadStatusResponse>
  deleteFile(fileId: string): Promise<{ success: boolean }>
}

export interface DocumentUploadResponse {
  id: string
  filename: string
  size: number
  content_type: string
  status: 'uploaded' | 'processing' | 'completed' | 'error'
  processing_status?: {
    text_extracted: boolean
    embeddings_created: boolean
    indexed: boolean
  }
  upload_url?: string
  error_message?: string
}

export interface ImageUploadResponse {
  id: string
  filename: string
  size: number
  content_type: string
  url: string
  thumbnail_url?: string
}

export interface UploadStatusResponse {
  id: string
  status: 'uploaded' | 'processing' | 'completed' | 'error'
  progress: number
  processing_stage?: string
  error_message?: string
  estimated_completion?: string
}

export class UploadApiServiceImpl extends ApiService implements UploadApiService {
  
  async uploadDocument(formData: FormData): Promise<DocumentUploadResponse> {
    const response = await this.makeRequestWithFormData('/documents/upload', {
      method: 'POST',
      body: formData,
    })
    return response
  }

  async uploadImage(formData: FormData): Promise<ImageUploadResponse> {
    const response = await this.makeRequestWithFormData('/upload/image', {
      method: 'POST', 
      body: formData,
    })
    return response
  }

  async getUploadStatus(uploadId: string): Promise<UploadStatusResponse> {
    return this.makeRequest(`/upload/status/${uploadId}`)
  }

  async deleteFile(fileId: string): Promise<{ success: boolean }> {
    return this.makeRequest(`/upload/${fileId}`, {
      method: 'DELETE',
    })
  }

  // Método especializado para uploads que no include content-type JSON
  private async makeRequestWithFormData<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = await this.getToken()
    
    const url = `${this.baseUrl}/api/v1${endpoint}`
    
    // Para FormData, NO incluir Content-Type header
    // El navegador lo manejará automáticamente con boundary
    const headers = {
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    }

    const response = await fetch(url, {
      ...options,
      headers,
    })

    if (response.status === 401) {
      const { redirect } = await import('@remix-run/node')
      throw redirect('/auth/sign-in')
    }

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`Upload Error: ${response.status} - ${error}`)
    }

    return response.json()
  }
}

/**
 * Factory function para crear el servicio de upload
 */
export async function createUploadApiService(args: LoaderFunctionArgs): Promise<UploadApiServiceImpl> {
  const { getAuth } = await import('@clerk/remix/ssr.server')
  const { userId, getToken } = getAuth(args)
  
  const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || 'http://localhost:8000'
  
  return new UploadApiServiceImpl({
    baseUrl: BACKEND_BASE_URL,
    getToken: async () => {
      try {
        const token = await getToken()
        return token
      } catch (error) {
        console.error('Error obteniendo token de Clerk:', error)
        return null
      }
    },
  })
}

/**
 * Utilidades para validar archivos antes del upload
 */
export const uploadValidation = {
  // Documentos permitidos
  documentTypes: [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain',
    'text/markdown',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  ],

  // Imágenes permitidas
  imageTypes: [
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/svg+xml',
  ],

  // Tamaños máximos (en bytes)
  maxSizes: {
    document: 50 * 1024 * 1024, // 50MB
    image: 10 * 1024 * 1024,    // 10MB
  },

  // Validar archivo de documento
  validateDocument(file: File): { isValid: boolean; error?: string } {
    if (!this.documentTypes.includes(file.type)) {
      return {
        isValid: false,
        error: `Tipo de archivo no soportado: ${file.type}. Tipos permitidos: PDF, Word, Excel, PowerPoint, Texto.`
      }
    }

    if (file.size > this.maxSizes.document) {
      return {
        isValid: false,
        error: `Archivo demasiado grande: ${(file.size / 1024 / 1024).toFixed(1)}MB. Máximo permitido: 50MB.`
      }
    }

    if (file.size === 0) {
      return {
        isValid: false,
        error: 'El archivo está vacío.'
      }
    }

    return { isValid: true }
  },

  // Validar archivo de imagen
  validateImage(file: File): { isValid: boolean; error?: string } {
    if (!this.imageTypes.includes(file.type)) {
      return {
        isValid: false,
        error: `Tipo de imagen no soportado: ${file.type}. Tipos permitidos: JPEG, PNG, GIF, WebP, SVG.`
      }
    }

    if (file.size > this.maxSizes.image) {
      return {
        isValid: false,
        error: `Imagen demasiado grande: ${(file.size / 1024 / 1024).toFixed(1)}MB. Máximo permitido: 10MB.`
      }
    }

    if (file.size === 0) {
      return {
        isValid: false,
        error: 'La imagen está vacía.'
      }
    }

    return { isValid: true }
  },

  // Obtener extensión de archivo
  getFileExtension(filename: string): string {
    return filename.split('.').pop()?.toLowerCase() || ''
  },

  // Formatear tamaño de archivo
  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes'
    
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  },

  // Generar nombre único para archivo
  generateUniqueFilename(originalName: string): string {
    const timestamp = Date.now()
    const random = Math.random().toString(36).substring(2, 8)
    const extension = this.getFileExtension(originalName)
    const baseName = originalName.replace(/\.[^/.]+$/, "").substring(0, 50)
    
    return `${baseName}_${timestamp}_${random}.${extension}`
  }
}

/**
 * Hook para progress de upload (para usar en el cliente)
 */
export interface UploadProgress {
  loaded: number
  total: number
  percentage: number
  status: 'idle' | 'uploading' | 'processing' | 'completed' | 'error'
  error?: string
}

/**
 * Utilidad para crear FormData desde un archivo
 */
export function createFileFormData(
  file: File, 
  additionalFields: Record<string, string> = {}
): FormData {
  const formData = new FormData()
  
  // Agregar el archivo
  formData.append('file', file)
  
  // Agregar campos adicionales
  Object.entries(additionalFields).forEach(([key, value]) => {
    formData.append(key, value)
  })
  
  return formData
}