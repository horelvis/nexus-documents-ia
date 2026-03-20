/**
 * Pure function to generate contextual follow-up suggestions
 * based on the user's query, Emma's response, and tools used.
 */
export function getContextualSuggestions(
  query?: string,
  response?: string,
  toolsUsed?: string[],
): string[] {
  const queryLower = (query || '').toLowerCase()
  const responseLower = (response || '').toLowerCase()

  // If tools were used (documents found), suggest follow-up actions
  if (toolsUsed && toolsUsed.length > 0) {
    if (toolsUsed.some(t => t.includes('search') || t.includes('semantic'))) {
      return [
        '¿Puedes resumir los documentos encontrados?',
        'Analiza los riesgos de estos documentos',
        '¿Qué otros documentos están relacionados?',
      ]
    }
    if (toolsUsed.some(t => t.includes('analyze'))) {
      return [
        '¿Qué acciones recomiendas?',
        'Explica los riesgos en detalle',
        '¿Hay problemas de cumplimiento?',
      ]
    }
  }

  // Contract-related queries
  if (queryLower.includes('contrato') || queryLower.includes('contract')) {
    return [
      '¿Cuáles son las cláusulas más importantes?',
      'Identifica los riesgos del contrato',
      '¿Cuándo vence este contrato?',
    ]
  }

  // Count/list queries
  if (queryLower.includes('cuántos') || queryLower.includes('cuantos') || queryLower.includes('lista')) {
    return [
      'Muestra los más recientes',
      '¿Cuáles requieren atención?',
      'Filtra por fecha',
    ]
  }

  // Document analysis
  if (queryLower.includes('analiza') || queryLower.includes('revisa') || queryLower.includes('verifica')) {
    return [
      '¿Qué riesgos encontraste?',
      'Resume los puntos clave',
      '¿Cumple con la normativa?',
    ]
  }

  // If response mentions documents were not found
  if (responseLower.includes('no se encontraron') || responseLower.includes('no encontré')) {
    return [
      'Buscar con términos diferentes',
      '¿Qué documentos tengo disponibles?',
      'Ayúdame a reformular la búsqueda',
    ]
  }

  // Greeting/intro - suggest getting started
  if (queryLower.includes('hola') || queryLower.includes('me llamo') || queryLower.includes('buenos')) {
    return [
      '¿Cuántos documentos tengo?',
      'Muestra mis contratos recientes',
      '¿Qué puedes hacer por mí?',
    ]
  }

  // Default contextual suggestions
  return [
    '¿Puedes darme más detalles?',
    'Muestra documentos relacionados',
    '¿Qué más puedo preguntarte?',
  ]
}
