declare module 'react-pdf' {
  import { ReactElement } from 'react'

  export interface DocumentProps {
    file: string | File | Uint8Array
    onLoadSuccess?: (pdf: { numPages: number }) => void
    onLoadError?: (error: Error) => void
    loading?: ReactElement | string | null
    className?: string
    children?: ReactElement | ReactElement[]
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