// Import pdfjs from react-pdf to ensure version consistency
import { pdfjs } from 'react-pdf'

// Configure PDF.js worker - uses local worker file copied from react-pdf's pdfjs-dist (v5.3.93)
// Using .js extension for better browser compatibility
export function configurePdfWorker() {
  if (typeof window !== 'undefined' && !pdfjs.GlobalWorkerOptions.workerSrc) {
    pdfjs.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.js'
  }
}

// Helper to convert document URL to PDF-compatible URL
export function getPdfUrl(documentId: string): string {
  // This assumes your backend returns a PDF preview at this endpoint
  return `/api/v1/documents/${documentId}/preview`
}

// Helper to validate if a URL returns a PDF
export async function validatePdfUrl(url: string): Promise<boolean> {
  try {
    const response = await fetch(url, { method: 'HEAD' })
    const contentType = response.headers.get('content-type')
    return contentType?.includes('application/pdf') || false
  } catch {
    return false
  }
}