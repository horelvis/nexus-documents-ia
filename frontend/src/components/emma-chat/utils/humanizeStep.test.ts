import { describe, it, expect } from 'vitest'
import { humanizeSteps } from './humanizeStep'
import type { RawReasoningStep } from './humanizeStep'

describe('humanizeSteps()', () => {
  it('returns empty for empty input', () => {
    expect(humanizeSteps([])).toEqual([])
  })

  // ─── Pipeline steps ──────────────────────────────────────────────────────

  it('skips Intent routing', () => {
    expect(humanizeSteps([
      { type: 'routing', content: 'Intent: document_query (confidence: 0.85)' },
    ])).toHaveLength(0)
  })

  it('shows rewrite when query was reformulated', () => {
    const result = humanizeSteps([
      { type: 'routing', content: "Rewrite: 'esos contratos' → 'contratos de ACME 2024'" },
    ])
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Reformulada: "contratos de ACME 2024"')
  })

  it('skips rewrite pass-throughs', () => {
    expect(humanizeSteps([
      { type: 'routing', content: 'Rewrite: no history, pass-through' },
    ])).toHaveLength(0)
    expect(humanizeSteps([
      { type: 'routing', content: 'Rewrite: query already self-contained' },
    ])).toHaveLength(0)
  })

  it('shows memory recall with doc count', () => {
    const result = humanizeSteps([
      { type: 'thinking', content: 'Memory recall: 5 documentos escaneados → pistas generadas' },
    ])
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Memoria consultada (5 docs)')
  })

  it('ignores generic thinking (LLM reasoning)', () => {
    expect(humanizeSteps([
      { type: 'thinking', content: 'I should analyze carefully...' },
    ])).toHaveLength(0)
  })

  // ─── smart_search — real backend format ──────────────────────────────────

  it('smart_search: extracts count from real backend format', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'smart_search(query=facturas de 2024, scope=documents)' },
      { type: 'tool_result', content: "Se encontraron 5 resultados para 'facturas de 2024':\n\n1. **Factura_001.pdf**", source: 'smart_search' },
    ])
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('5 resultados encontrados')
    expect(result[0].status).toBe('completed')
    expect(result[0].icon).toBe('search')
  })

  it('smart_search: handles "no results" format', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'smart_search(query=nanotecnología)' },
      { type: 'tool_result', content: "No se encontraron resultados para: 'nanotecnología'", source: 'smart_search' },
    ])
    expect(result[0].text).toBe('Sin resultados')
  })

  it('smart_search: active text includes query', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'smart_search(query=contratos ACME, scope=auto)' },
    ])
    expect(result[0].status).toBe('active')
    expect(result[0].text).toBe('Buscando "contratos ACME"...')
  })

  // ─── get_document_content — real backend format ─────────────────────────

  it('get_document_content: extracts title from real format', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'get_document_content(document_id=abc123)' },
      { type: 'tool_result', content: '**Documento: Contrato de Servicios ACME**\nTipo: contrato\nFecha: 2024-01-15\n\nContenido del doc...', source: 'get_document_content' },
    ])
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Leí "Contrato de Servicios ACME"')
    expect(result[0].icon).toBe('read')
  })

  it('get_document_content: falls back to "Documento leído" if no title', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'get_document_content(document_id=xyz)' },
      { type: 'tool_result', content: 'Raw content without document header...', source: 'get_document_content' },
    ])
    expect(result[0].text).toBe('Documento leído')
  })

  // ─── structural_query — real backend format ─────────────────────────────

  it('structural_query: extracts count from real format', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'structural_query(query=total documentos, max_results=1)' },
      { type: 'tool_result', content: '**Total de documentos**: 15\n**Desglose por tipo**:\n- contrato: 8', source: 'structural_query' },
    ])
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('15 documentos en el grafo')
    expect(result[0].icon).toBe('analyze')
  })

  // ─── web_search ─────────────────────────────────────────────────────────

  it('web_search: active text with query', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'web_search(query=noticias Madrid)' },
    ])
    expect(result[0].text).toBe('Buscando en internet "noticias Madrid"...')
  })

  it('web_search: completed text', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'web_search(query=noticias)' },
      { type: 'tool_result', content: 'Search results...', source: 'web_search' },
    ])
    expect(result[0].text).toBe('Resultados de internet obtenidos')
    expect(result[0].icon).toBe('web')
  })

  // ─── search_jurisprudence ───────────────────────────────────────────────

  it('search_jurisprudence: active with query', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'search_jurisprudence(query=despido improcedente)' },
    ])
    expect(result[0].text).toBe('Buscando jurisprudencia: "despido improcedente"...')
    expect(result[0].icon).toBe('legal')
  })

  // ─── Unknown tool fallback ──────────────────────────────────────────────

  it('unknown tool: shows "Paso completado" for completed', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'unknown_tool(param=value)' },
      { type: 'tool_result', content: 'Some result', source: 'unknown_tool' },
    ])
    expect(result[0].text).toBe('Paso completado')
    expect(result[0].icon).toBe('analyze')
  })

  it('unknown tool: shows "Procesando..." when active', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'unknown_tool(param=value)' },
    ])
    expect(result[0].text).toBe('Procesando...')
  })

  // ─── Ignored types ──────────────────────────────────────────────────────

  it('ignores response steps', () => {
    expect(humanizeSteps([
      { type: 'response', content: 'Final answer' },
    ])).toHaveLength(0)
  })

  it('ignores error steps', () => {
    expect(humanizeSteps([
      { type: 'error', content: 'Something failed' },
    ])).toHaveLength(0)
  })

  // ─── Multiple tool calls (distinct steps, no duplicates) ────────────────

  it('multiple different tools produce distinct steps', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'smart_search(query=contratos ACME)' },
      { type: 'tool_result', content: "Se encontraron 3 resultados para 'contratos ACME':\n...", source: 'smart_search' },
      { type: 'tool_call', content: 'get_document_content(document_id=abc)' },
      { type: 'tool_result', content: '**Documento: Contrato ACME 2024**\nTipo: contrato\n\n...', source: 'get_document_content' },
      { type: 'tool_call', content: 'structural_query(query=total)' },
      { type: 'tool_result', content: '**Total de documentos**: 10\n...', source: 'structural_query' },
    ])
    expect(result).toHaveLength(3)
    expect(result[0].text).toBe('3 resultados encontrados')
    expect(result[1].text).toBe('Leí "Contrato ACME 2024"')
    expect(result[2].text).toBe('10 documentos en el grafo')
  })

  it('two smart_search calls produce distinguishable steps', () => {
    const result = humanizeSteps([
      { type: 'tool_call', content: 'smart_search(query=facturas)' },
      { type: 'tool_result', content: "Se encontraron 5 resultados para 'facturas':\n...", source: 'smart_search' },
      { type: 'tool_call', content: 'smart_search(query=contratos laborales)' },
      { type: 'tool_result', content: "Se encontraron 2 resultados para 'contratos laborales':\n...", source: 'smart_search' },
    ])
    expect(result).toHaveLength(2)
    expect(result[0].text).toBe('5 resultados encontrados')
    expect(result[1].text).toBe('2 resultados encontrados')
  })

  // ─── Full pipeline simulation ────────────────────────────────────────────

  it('full pipeline: rewrite → memory → search → read', () => {
    const result = humanizeSteps([
      { type: 'routing', content: 'Intent: document_query (confidence: 0.92)' },
      { type: 'routing', content: "Rewrite: 'esos contratos' → 'contratos de trabajo ACME'" },
      { type: 'thinking', content: 'Memory recall: 3 documentos escaneados → pistas generadas' },
      { type: 'thinking', content: 'I need to search for the contracts...' },
      { type: 'tool_call', content: 'smart_search(query=contratos de trabajo ACME)' },
      { type: 'tool_result', content: "Se encontraron 4 resultados para 'contratos':\n...", source: 'smart_search' },
      { type: 'thinking', content: 'Let me read the most relevant document...' },
      { type: 'tool_call', content: 'get_document_content(document_id=doc123)' },
      { type: 'tool_result', content: '**Documento: Contrato ACME 2024**\nTipo: contrato\n\n...', source: 'get_document_content' },
      { type: 'response', content: 'Based on the analysis...' },
    ])
    expect(result).toHaveLength(4)
    expect(result[0].text).toBe('Reformulada: "contratos de trabajo ACME"')
    expect(result[1].text).toBe('Memoria consultada (3 docs)')
    expect(result[2].text).toBe('4 resultados encontrados')
    expect(result[3].text).toBe('Leí "Contrato ACME 2024"')
    expect(result.every(s => s.status === 'completed')).toBe(true)
  })

  it('simple query: only tool step, no noise', () => {
    const result = humanizeSteps([
      { type: 'routing', content: 'Intent: structural_query (confidence: 0.95)' },
      { type: 'routing', content: 'Rewrite: no history, pass-through' },
      { type: 'tool_call', content: 'structural_query(query=total de documentos)' },
      { type: 'tool_result', content: '**Total de documentos**: 15\n**Desglose...', source: 'structural_query' },
      { type: 'response', content: 'Tienes 15 documentos.' },
    ])
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('15 documentos en el grafo')
  })

  it('streaming mid-tool: shows active search with query', () => {
    const result = humanizeSteps([
      { type: 'routing', content: 'Intent: document_query (confidence: 0.90)' },
      { type: 'routing', content: 'Rewrite: query already self-contained' },
      { type: 'thinking', content: 'Memory recall: 2 documentos escaneados → pistas generadas' },
      { type: 'tool_call', content: 'smart_search(query=facturas 2024)' },
    ])
    expect(result).toHaveLength(2)
    expect(result[0].text).toBe('Memoria consultada (2 docs)')
    expect(result[1].text).toBe('Buscando "facturas 2024"...')
    expect(result[1].status).toBe('active')
  })

  // ─── Unique IDs ──────────────────────────────────────────────────────────

  it('assigns unique ids', () => {
    const result = humanizeSteps([
      { type: 'routing', content: "Rewrite: 'a' → 'b'" },
      { type: 'tool_call', content: 'smart_search(query=a)' },
      { type: 'tool_result', content: "Se encontraron 1 resultado para 'a':\n...", source: 'smart_search' },
      { type: 'tool_call', content: 'web_search(query=b)' },
      { type: 'tool_result', content: 'Results', source: 'web_search' },
    ])
    const ids = result.map(s => s.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})
