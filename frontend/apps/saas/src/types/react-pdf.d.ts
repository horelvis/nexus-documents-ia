declare module 'react-pdf' {
  import { ReactElement, ReactNode } from 'react'

  export type PdfSource =
    | string
    | File
    | Uint8Array
    | {
        url: string
        httpHeaders?: Record<string, string>
        withCredentials?: boolean
      }

  export interface DocumentProps {
    file: PdfSource
    options?: Record<string, any>
    onLoadSuccess?: (pdf: { numPages: number }) => void
    onLoadError?: (error: Error) => void
    loading?: ReactElement | string | null
    className?: string
    children?: ReactNode
  }

  export interface PageProps {
    pageNumber: number
    scale?: number
    rotate?: number
    className?: string
    loading?: ReactElement | string | null
  }

  export const Document: React.ComponentType<DocumentProps>
  export const Page: React.ComponentType<PageProps>
  
  export const pdfjs: {
    version: string
    GlobalWorkerOptions: {
      workerSrc: string
    }
  }
}
