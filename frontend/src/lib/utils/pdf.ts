import * as pdfjs from 'pdfjs-dist'

// Configure PDF.js worker
export function configurePdfWorker() {
  if (typeof window !== 'undefined' && !pdfjs.GlobalWorkerOptions.workerSrc) {
    pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`
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