import { describe, it, expect } from 'vitest'
import { humanizeSteps } from './humanizeStep'
import type { RawReasoningStep } from './humanizeStep'

describe('humanizeSteps()', () => {
  // 1. Empty input
  it('returns empty array for empty input', () => {
    expect(humanizeSteps([])).toEqual([])
  })

  // 2. smart_search tool_call + tool_result → single merged step with count
  it('merges smart_search tool_call and tool_result into one step', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'smart_search(query=contratos, stores=documents)' },
      { type: 'tool_result', content: 'Found 5 results for query', source: 'smart_search' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Encontré 5 documentos relevantes')
    expect(result[0].status).toBe('completed')
    expect(result[0].icon).toBe('search')
  })

  // 3. get_document_content → read step with extracted filename
  it('merges get_document_content with filename from result', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'get_document_content(id=abc123)' },
      { type: 'tool_result', content: 'Content of contrato_servicio.pdf retrieved', source: 'get_document_content' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Leí contrato_servicio.pdf')
    expect(result[0].status).toBe('completed')
    expect(result[0].icon).toBe('read')
  })

  // 4. structural_query → analyze step with document count
  it('merges structural_query with document count', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'structural_query(type=count)' },
      { type: 'tool_result', content: 'Total de documentos**: 42 en el sistema', source: 'structural_query' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('El grafo reportó 42 documentos')
    expect(result[0].status).toBe('completed')
    expect(result[0].icon).toBe('analyze')
  })

  // 5. web_search → web icon
  it('uses web icon for web_search', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'web_search(query=noticias)' },
      { type: 'tool_result', content: 'Search results from the internet', source: 'web_search' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].icon).toBe('web')
    expect(result[0].text).toBe('Resultados de internet obtenidos')
    expect(result[0].status).toBe('completed')
  })

  // 6. search_jurisprudence → legal icon
  it('uses legal icon for search_jurisprudence', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'search_jurisprudence(query=sentencia)' },
      { type: 'tool_result', content: 'Jurisprudencia results returned', source: 'search_jurisprudence' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].icon).toBe('legal')
    expect(result[0].text).toBe('Jurisprudencia encontrada')
    expect(result[0].status).toBe('completed')
  })

  // 7. thinking steps are ignored
  it('ignores thinking steps', () => {
    const steps: RawReasoningStep[] = [
      { type: 'thinking', content: 'I should analyze the documents carefully...' },
      { type: 'tool_call', content: 'smart_search(query=facturas)' },
      { type: 'tool_result', content: 'Found 3 results for query', source: 'smart_search' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Encontré 3 documentos relevantes')
  })

  // 8. routing steps are ignored
  it('ignores routing steps', () => {
    const steps: RawReasoningStep[] = [
      { type: 'routing', content: 'Routing to document_query handler' },
      { type: 'tool_call', content: 'smart_search(query=nominas)' },
      { type: 'tool_result', content: 'Found 7 results for query', source: 'smart_search' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Encontré 7 documentos relevantes')
  })

  // 9. Deduplication: tool_call replaced by tool_result (no duplicate)
  it('does not produce duplicate steps when tool_call is followed by tool_result', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'smart_search(query=contratos)' },
      { type: 'tool_result', content: 'Found 2 results for query', source: 'smart_search' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
  })

  // 10. Standalone tool_call (no result) → active status
  it('marks standalone tool_call without result as active', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'smart_search(query=facturas)' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('active')
    expect(result[0].icon).toBe('search')
    expect(result[0].text).toBe('Buscando información...')
  })

  // 10b. Standalone get_document_content active text
  it('shows correct active text for get_document_content without result', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'get_document_content(id=xyz)' },
    ]
    const result = humanizeSteps(steps)
    expect(result[0].status).toBe('active')
    expect(result[0].text).toBe('Leyendo documento...')
    expect(result[0].icon).toBe('read')
  })

  // 10c. Standalone structural_query active text
  it('shows correct active text for structural_query without result', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'structural_query(type=list)' },
    ]
    const result = humanizeSteps(steps)
    expect(result[0].status).toBe('active')
    expect(result[0].text).toBe('Consultando el grafo de conocimiento...')
    expect(result[0].icon).toBe('analyze')
  })

  // 11. Unknown tool → "Procesando..." fallback with analyze icon
  it('shows Procesando... for unknown tools', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'some_unknown_tool(param=value)' },
      { type: 'tool_result', content: 'Some result returned', source: 'some_unknown_tool' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Procesando...')
    expect(result[0].icon).toBe('analyze')
    expect(result[0].status).toBe('completed')
  })

  // 12. Multiple sequential tool calls → correct number of steps
  it('handles multiple sequential tool calls correctly', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'smart_search(query=contratos)' },
      { type: 'tool_result', content: 'Found 3 results for query', source: 'smart_search' },
      { type: 'tool_call', content: 'get_document_content(id=abc)' },
      { type: 'tool_result', content: 'Content of informe_anual.pdf retrieved', source: 'get_document_content' },
      { type: 'tool_call', content: 'structural_query(type=count)' },
      { type: 'tool_result', content: 'Total de documentos**: 10 en el sistema', source: 'structural_query' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(3)
    expect(result[0].text).toBe('Encontré 3 documentos relevantes')
    expect(result[1].text).toBe('Leí informe_anual.pdf')
    expect(result[2].text).toBe('El grafo reportó 10 documentos')
  })

  // 12b. Multiple sequential tool calls interleaved with thinking → thinking ignored
  it('ignores thinking steps between tool calls', () => {
    const steps: RawReasoningStep[] = [
      { type: 'thinking', content: 'First I should search...' },
      { type: 'tool_call', content: 'smart_search(query=facturas)' },
      { type: 'tool_result', content: 'Found 1 results for query', source: 'smart_search' },
      { type: 'thinking', content: 'Now I should read the document...' },
      { type: 'tool_call', content: 'get_document_content(id=def)' },
      { type: 'tool_result', content: 'Content of factura_enero.pdf retrieved', source: 'get_document_content' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(2)
    expect(result[0].icon).toBe('search')
    expect(result[1].icon).toBe('read')
  })

  // Additional: smart_search result without count falls back gracefully
  it('falls back gracefully for smart_search result without count', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'smart_search(query=algo)' },
      { type: 'tool_result', content: 'No specific count in this result', source: 'smart_search' },
    ]
    const result = humanizeSteps(steps)
    expect(result[0].status).toBe('completed')
    expect(result[0].icon).toBe('search')
    // Should still produce a meaningful string (not crash)
    expect(typeof result[0].text).toBe('string')
    expect(result[0].text.length).toBeGreaterThan(0)
  })

  // Additional: each step gets a unique id
  it('assigns unique ids to all steps', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'smart_search(query=a)' },
      { type: 'tool_result', content: 'Found 1 results for query', source: 'smart_search' },
      { type: 'tool_call', content: 'web_search(query=b)' },
      { type: 'tool_result', content: 'Web results', source: 'web_search' },
    ]
    const result = humanizeSteps(steps)
    const ids = result.map(s => s.id)
    const unique = new Set(ids)
    expect(unique.size).toBe(ids.length)
  })

  // web_search active text
  it('shows correct active text for web_search without result', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'web_search(query=noticias)' },
    ]
    const result = humanizeSteps(steps)
    expect(result[0].status).toBe('active')
    expect(result[0].text).toBe('Buscando en internet...')
    expect(result[0].icon).toBe('web')
  })

  // search_jurisprudence active text
  it('shows correct active text for search_jurisprudence without result', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'search_jurisprudence(query=sentencia)' },
    ]
    const result = humanizeSteps(steps)
    expect(result[0].status).toBe('active')
    expect(result[0].text).toBe('Buscando jurisprudencia...')
    expect(result[0].icon).toBe('legal')
  })
})
