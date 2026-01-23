/**
 * Legal References Parser
 *
 * Detects Spanish legal references in text and converts them to clickable BOE links.
 * Supports: Leyes Orgánicas, Estatuto de los Trabajadores, LOPDGDD, RGPD, etc.
 */

import React from 'react'
import { ExternalLink } from 'lucide-react'

// Known BOE document identifiers
const BOE_IDENTIFIERS: Record<string, string> = {
  // Estatuto de los Trabajadores (Real Decreto Legislativo 2/2015)
  'ET': 'BOE-A-2015-11430',
  'Estatuto de los Trabajadores': 'BOE-A-2015-11430',

  // LOPDGDD (Ley Orgánica 3/2018)
  'LOPDGDD': 'BOE-A-2018-16673',
  'Ley Orgánica 3/2018': 'BOE-A-2018-16673',

  // Ley de Igualdad (Ley Orgánica 3/2007)
  'Ley Orgánica 3/2007': 'BOE-A-2007-6115',

  // Código Civil
  'Código Civil': 'BOE-A-1889-4763',

  // Ley General Tributaria
  'Ley General Tributaria': 'BOE-A-2003-23186',
  'LGT': 'BOE-A-2003-23186',

  // LAU - Ley de Arrendamientos Urbanos
  'LAU': 'BOE-A-1994-26003',
  'Ley de Arrendamientos Urbanos': 'BOE-A-1994-26003',

  // Ley de Sociedades de Capital
  'LSC': 'BOE-A-2010-10544',
  'Ley de Sociedades de Capital': 'BOE-A-2010-10544',
}

// Patterns to detect legal references
interface LegalPattern {
  regex: RegExp
  getBoeId: (match: RegExpMatchArray) => string | null
  getDisplayText: (match: RegExpMatchArray) => string
}

const LEGAL_PATTERNS: LegalPattern[] = [
  // Ley Orgánica X/YYYY
  {
    regex: /Ley Orgánica (\d+)\/(\d{4})(?:,?\s*de\s*\d+\s*de\s*\w+)?(?:,?\s*(?:de|para|sobre)\s+[^.]+)?/gi,
    getBoeId: (match) => {
      const num = match[1]
      const year = match[2]
      // Known mappings
      if (num === '3' && year === '2007') return 'BOE-A-2007-6115'
      if (num === '3' && year === '2018') return 'BOE-A-2018-16673'
      if (num === '1' && year === '2004') return 'BOE-A-2004-21760' // Violencia de género
      if (num === '2' && year === '2006') return 'BOE-A-2006-7899' // Educación
      // Return null for unknown - will search by text
      return null
    },
    getDisplayText: (match) => match[0]
  },

  // Real Decreto Legislativo X/YYYY
  {
    regex: /Real Decreto Legislativo (\d+)\/(\d{4})/gi,
    getBoeId: (match) => {
      const num = match[1]
      const year = match[2]
      if (num === '2' && year === '2015') return 'BOE-A-2015-11430' // ET
      if (num === '1' && year === '2010') return 'BOE-A-2010-10544' // LSC
      return null
    },
    getDisplayText: (match) => match[0]
  },

  // Artículo X del/de la/del ET/Estatuto de los Trabajadores
  {
    regex: /Art(?:ículo)?\.?\s*(\d+(?:\.\d+)?)\s*(?:del?\s*)?(?:ET|Estatuto de los Trabajadores)/gi,
    getBoeId: () => 'BOE-A-2015-11430',
    getDisplayText: (match) => match[0]
  },

  // LOPDGDD standalone
  {
    regex: /\bLOPDGDD\b/gi,
    getBoeId: () => 'BOE-A-2018-16673',
    getDisplayText: (match) => match[0]
  },

  // RGPD / GDPR
  {
    regex: /\b(?:RGPD|GDPR|Reglamento\s*(?:\(UE\))?\s*2016\/679)\b/gi,
    getBoeId: () => null, // External EU regulation
    getDisplayText: (match) => match[0]
  },

  // Ley X/YYYY (general laws)
  {
    regex: /Ley (\d+)\/(\d{4})(?:,?\s*de\s*\d+\s*de\s*\w+)?/gi,
    getBoeId: (match) => {
      const num = match[1]
      const year = match[2]
      // Known laws
      if (num === '58' && year === '2003') return 'BOE-A-2003-23186' // LGT
      if (num === '29' && year === '1994') return 'BOE-A-1994-26003' // LAU
      return null
    },
    getDisplayText: (match) => match[0]
  }
]

/**
 * Generate BOE URL from identifier
 */
function getBoeUrl(boeId: string): string {
  return `https://www.boe.es/buscar/act.php?id=${boeId}`
}

/**
 * Generate BOE search URL for unknown references
 */
function getBoeSearchUrl(searchText: string): string {
  const encoded = encodeURIComponent(searchText)
  return `https://www.boe.es/buscar/?texto=${encoded}&tipo=1`
}

/**
 * Get RGPD EUR-Lex URL
 */
function getRgpdUrl(): string {
  return 'https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:32016R0679'
}

interface LegalReference {
  text: string
  url: string
  startIndex: number
  endIndex: number
}

/**
 * Extract all legal references from text
 */
export function extractLegalReferences(text: string): LegalReference[] {
  const references: LegalReference[] = []
  const seenRanges = new Set<string>()

  for (const pattern of LEGAL_PATTERNS) {
    let match
    const regex = new RegExp(pattern.regex.source, pattern.regex.flags)

    while ((match = regex.exec(text)) !== null) {
      const startIndex = match.index
      const endIndex = match.index + match[0].length
      const rangeKey = `${startIndex}-${endIndex}`

      // Skip if we already have a reference at this position
      if (seenRanges.has(rangeKey)) continue

      const boeId = pattern.getBoeId(match)
      let url: string

      if (match[0].match(/RGPD|GDPR/i)) {
        url = getRgpdUrl()
      } else if (boeId) {
        url = getBoeUrl(boeId)
      } else {
        url = getBoeSearchUrl(pattern.getDisplayText(match))
      }

      references.push({
        text: match[0],
        url,
        startIndex,
        endIndex
      })

      seenRanges.add(rangeKey)
    }
  }

  // Sort by position
  return references.sort((a, b) => a.startIndex - b.startIndex)
}

/**
 * Parse text and return React elements with clickable legal references
 */
export function parseLegalReferences(text: string): React.ReactNode {
  if (!text) return null

  const references = extractLegalReferences(text)

  if (references.length === 0) {
    return text
  }

  const elements: React.ReactNode[] = []
  let lastIndex = 0

  references.forEach((ref, idx) => {
    // Add text before this reference
    if (ref.startIndex > lastIndex) {
      elements.push(text.slice(lastIndex, ref.startIndex))
    }

    // Add the linked reference
    elements.push(
      <a
        key={`ref-${idx}`}
        href={ref.url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-0.5 text-primary hover:underline font-medium"
        onClick={(e) => e.stopPropagation()}
      >
        {ref.text}
        <ExternalLink className="h-3 w-3 inline-block ml-0.5" />
      </a>
    )

    lastIndex = ref.endIndex
  })

  // Add remaining text
  if (lastIndex < text.length) {
    elements.push(text.slice(lastIndex))
  }

  return <>{elements}</>
}

/**
 * Get unique legal references for display as a list
 */
export function getUniqueLegalReferences(text: string): Array<{ text: string; url: string }> {
  const references = extractLegalReferences(text)
  const seen = new Set<string>()
  const unique: Array<{ text: string; url: string }> = []

  for (const ref of references) {
    // Normalize the reference text for deduplication
    const normalized = ref.text.toLowerCase().replace(/\s+/g, ' ')
    if (!seen.has(normalized)) {
      seen.add(normalized)
      unique.push({ text: ref.text, url: ref.url })
    }
  }

  return unique
}

// Export BOE_IDENTIFIERS for external use
export { BOE_IDENTIFIERS }
