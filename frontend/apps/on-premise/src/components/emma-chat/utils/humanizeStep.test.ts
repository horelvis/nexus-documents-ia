import { describe, it, expect } from 'vitest'
import { humanizeSteps } from './humanizeStep'
import type { RawReasoningStep } from './humanizeStep'

describe('humanizeSteps()', () => {
  // ─── Empty input ─────────────────────────────────────────────────────────
  it('returns empty array for empty input', () => {
    expect(humanizeSteps([])).toEqual([])
  })

  // ─── Pipeline steps (routing/thinking with known content) ────────────────

  it('shows classify step from Intent routing', () => {
    const steps: RawReasoningStep[] = [
      { type: 'routing', content: 'Intent: document_query (confidence: 0.85)' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Clasificada como document query')
    expect(result[0].icon).toBe('analyze')
    expect(result[0].status).toBe('completed')
  })

  it('shows rewrite step when query was reformulated', () => {
    const steps: RawReasoningStep[] = [
      { type: 'routing', content: "Rewrite: 'esos contratos' → 'contratos de ACME 2024'" },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Consulta reformulada')
    expect(result[0].icon).toBe('analyze')
    expect(result[0].status).toBe('completed')
  })

  it('skips rewrite pass-through (no history)', () => {
    const steps: RawReasoningStep[] = [
      { type: 'routing', content: 'Rewrite: no history, pass-through' },
    ]
    expect(humanizeSteps(steps)).toHaveLength(0)
  })

  it('skips rewrite pass-through (query already self-contained)', () => {
    const steps: RawReasoningStep[] = [
      { type: 'routing', content: 'Rewrite: query already self-contained' },
    ]
    expect(humanizeSteps(steps)).toHaveLength(0)
  })

  it('skips rewrite when skipped due to error', () => {
    const steps: RawReasoningStep[] = [
      { type: 'routing', content: 'Rewrite: skipped (error: timeout)' },
    ]
    expect(humanizeSteps(steps)).toHaveLength(0)
  })

  it('shows memory recall step with document count', () => {
    const steps: RawReasoningStep[] = [
      { type: 'thinking', content: 'Memory recall: 5 documentos escaneados → pistas de búsqueda generadas' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Memoria consultada (5 docs)')
    expect(result[0].icon).toBe('search')
    expect(result[0].status).toBe('completed')
  })

  it('ignores generic thinking steps (LLM internal reasoning)', () => {
    const steps: RawReasoningStep[] = [
      { type: 'thinking', content: 'I should analyze the documents carefully...' },
    ]
    expect(humanizeSteps(steps)).toHaveLength(0)
  })

  it('ignores generic routing steps with no recognized pattern', () => {
    const steps: RawReasoningStep[] = [
      { type: 'routing', content: 'Routing to some unknown handler' },
    ]
    expect(humanizeSteps(steps)).toHaveLength(0)
  })

  // ─── Tool call merging ──────────────────────────────────────────────────

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

  it('merges get_document_content with filename from result', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'get_document_content(id=abc123)' },
      { type: 'tool_result', content: 'Content of contrato_servicio.pdf retrieved', source: 'get_document_content' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Leí contrato_servicio.pdf')
    expect(result[0].icon).toBe('read')
  })

  it('merges structural_query with document count', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'structural_query(type=count)' },
      { type: 'tool_result', content: 'Total de documentos**: 42 en el sistema', source: 'structural_query' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('El grafo reportó 42 documentos')
    expect(result[0].icon).toBe('analyze')
  })

  it('uses web icon for web_search', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'web_search(query=noticias)' },
      { type: 'tool_result', content: 'Search results from the internet', source: 'web_search' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].icon).toBe('web')
    expect(result[0].text).toBe('Resultados de internet obtenidos')
  })

  it('uses legal icon for search_jurisprudence', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'search_jurisprudence(query=sentencia)' },
      { type: 'tool_result', content: 'Jurisprudencia results returned', source: 'search_jurisprudence' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].icon).toBe('legal')
  })

  // ─── Standalone tool calls (active / in-flight) ──────────────────────────

  it('marks standalone tool_call without result as active', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'smart_search(query=facturas)' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].status).toBe('active')
    expect(result[0].text).toBe('Buscando información...')
  })

  it('shows correct active text for get_document_content', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'get_document_content(id=xyz)' },
    ]
    const result = humanizeSteps(steps)
    expect(result[0].status).toBe('active')
    expect(result[0].text).toBe('Leyendo documento...')
  })

  it('shows correct active text for web_search', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'web_search(query=noticias)' },
    ]
    const result = humanizeSteps(steps)
    expect(result[0].text).toBe('Buscando en internet...')
  })

  // ─── Unknown tool fallback ──────────────────────────────────────────────

  it('shows Procesando... for unknown tools', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'some_unknown_tool(param=value)' },
      { type: 'tool_result', content: 'Some result returned', source: 'some_unknown_tool' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Procesando...')
    expect(result[0].icon).toBe('analyze')
  })

  // ─── Silently ignored types ──────────────────────────────────────────────

  it('ignores response steps (synthesize phase)', () => {
    const steps: RawReasoningStep[] = [
      { type: 'response', content: 'Final answer: ...' },
    ]
    expect(humanizeSteps(steps)).toHaveLength(0)
  })

  it('ignores error steps', () => {
    const steps: RawReasoningStep[] = [
      { type: 'error', content: 'Something went wrong' },
    ]
    expect(humanizeSteps(steps)).toHaveLength(0)
  })

  // ─── Full pipeline simulation ────────────────────────────────────────────

  it('shows full pipeline: classify → rewrite → memory → search → read', () => {
    const steps: RawReasoningStep[] = [
      { type: 'routing', content: 'Intent: document_query (confidence: 0.92)' },
      { type: 'routing', content: "Rewrite: 'esos contratos' → 'contratos de trabajo ACME 2024'" },
      { type: 'thinking', content: 'Memory recall: 3 documentos escaneados → pistas de búsqueda generadas' },
      { type: 'thinking', content: 'I need to search for the contracts...' },
      { type: 'tool_call', content: 'smart_search(query=contratos de trabajo ACME 2024)' },
      { type: 'tool_result', content: 'Found 4 results for query', source: 'smart_search' },
      { type: 'thinking', content: 'Let me read the most relevant document...' },
      { type: 'tool_call', content: 'get_document_content(id=doc123)' },
      { type: 'tool_result', content: 'Content of contrato_ACME.pdf retrieved', source: 'get_document_content' },
      { type: 'response', content: 'Based on the analysis...' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(5)
    expect(result[0].text).toBe('Clasificada como document query')
    expect(result[1].text).toBe('Consulta reformulada')
    expect(result[2].text).toBe('Memoria consultada (3 docs)')
    expect(result[3].text).toBe('Encontré 4 documentos relevantes')
    expect(result[4].text).toBe('Leí contrato_ACME.pdf')
    // All completed
    expect(result.every(s => s.status === 'completed')).toBe(true)
  })

  it('shows pipeline with active search (streaming mid-tool)', () => {
    const steps: RawReasoningStep[] = [
      { type: 'routing', content: 'Intent: document_query (confidence: 0.90)' },
      { type: 'routing', content: 'Rewrite: query already self-contained' },
      { type: 'thinking', content: 'Memory recall: 2 documentos escaneados → pistas de búsqueda generadas' },
      { type: 'tool_call', content: 'smart_search(query=facturas 2024)' },
      // No tool_result yet — search in progress
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(3) // classify + memory + active search (rewrite skipped)
    expect(result[0].text).toBe('Clasificada como document query')
    expect(result[0].status).toBe('completed')
    expect(result[1].text).toBe('Memoria consultada (2 docs)')
    expect(result[1].status).toBe('completed')
    expect(result[2].text).toBe('Buscando información...')
    expect(result[2].status).toBe('active')
  })

  // ─── Multiple sequential tool calls ──────────────────────────────────────

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

  // ─── Unique IDs ──────────────────────────────────────────────────────────

  it('assigns unique ids to all steps', () => {
    const steps: RawReasoningStep[] = [
      { type: 'routing', content: 'Intent: document_query (confidence: 0.85)' },
      { type: 'tool_call', content: 'smart_search(query=a)' },
      { type: 'tool_result', content: 'Found 1 results for query', source: 'smart_search' },
      { type: 'tool_call', content: 'web_search(query=b)' },
      { type: 'tool_result', content: 'Web results', source: 'web_search' },
    ]
    const result = humanizeSteps(steps)
    const ids = result.map(s => s.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  // ─── Edge cases ──────────────────────────────────────────────────────────

  it('falls back for smart_search result without count', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'smart_search(query=algo)' },
      { type: 'tool_result', content: 'No specific count in this result', source: 'smart_search' },
    ]
    const result = humanizeSteps(steps)
    expect(result[0].status).toBe('completed')
    expect(result[0].text).toBe('Documentos encontrados')
  })
})
