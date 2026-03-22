'use client'

import { useState } from 'react'
import { IconDownload, IconFileText } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'

export function GeneratedDocDownload({ docId }: { docId: string }) {
  const [downloading, setDownloading] = useState(false)

  const handleDownload = async () => {
    if (downloading) return
    setDownloading(true)
    try {
      const { apiClient } = await import('@/lib/api-client')
      const result = await apiClient.downloadBlob(`/emma/generated/${docId}/download`)
      if (result.error || !result.blob) throw new Error(result.error || 'Download failed')
      const blobUrl = URL.createObjectURL(result.blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = `documento_generado_${docId}.docx`
      a.click()
      URL.revokeObjectURL(blobUrl)
    } catch (err) {
      console.error('DOCX download failed:', err)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="flex items-center gap-2 mt-3 p-2.5 rounded-lg bg-violet-500/10 border border-violet-500/20">
      <IconFileText className="h-5 w-5 text-violet-600 flex-shrink-0" />
      <span className="text-xs text-violet-700 dark:text-violet-400 flex-1">
        Documento DOCX generado y listo para descargar
      </span>
      <Button
        variant="outline"
        size="sm"
        onClick={handleDownload}
        disabled={downloading}
        className="gap-1.5 text-xs border-violet-500/30 text-violet-600 hover:bg-violet-500/10"
      >
        <IconDownload className="h-3.5 w-3.5" />
        {downloading ? 'Descargando...' : 'Descargar DOCX'}
      </Button>
    </div>
  )
}
