/**
 * useForgeDetection — Detects forge metadata from completed messages.
 *
 * Watches for forge_result messages and extracts forge metadata
 * for the artifacts panel. Thin hook, ~30 lines.
 */
import { useState, useEffect } from 'react'
import type { EmmaMessage, ForgeMetadata } from '@/lib/types/emma'

export function useForgeDetection(messages: EmmaMessage[]) {
  const [forgeMetadata, setForgeMetadata] = useState<ForgeMetadata | null>(null)

  // Watch messages for forge results
  useEffect(() => {
    const lastForge = [...messages]
      .reverse()
      .find((m) => m.type === 'forge_result' && m.forge)

    if (lastForge?.forge) {
      setForgeMetadata(prev => {
        if (prev && prev === lastForge.forge) return prev
        return lastForge.forge!
      })
    }
  }, [messages])

  return { forgeMetadata, setForgeMetadata }
}
