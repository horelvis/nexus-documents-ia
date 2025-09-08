"use client"

interface BPMNVisualizerProps {
  bpmnText: string
}

export function BPMNVisualizer({ bpmnText }: BPMNVisualizerProps) {
  const lines = bpmnText.split('\n').filter(line => line.trim() !== '')
  
  const getElementType = (line: string) => {
    const trimmed = line.trim()
    if (trimmed.includes('START_EVENT')) return 'start'
    if (trimmed.includes('END_EVENT')) return 'end'
    if (trimmed.includes('SERVICE_TASK')) return 'service'
    if (trimmed.includes('USER_TASK')) return 'user'
    if (trimmed.includes('EXCLUSIVE_GATEWAY')) return 'gateway'
    if (trimmed === '→' || trimmed.startsWith('├─') || trimmed.startsWith('└─')) return 'arrow'
    if (trimmed.startsWith('│')) return 'branch'
    return 'text'
  }

  const getElementStyle = (type: string) => {
    switch (type) {
      case 'start':
        return 'bg-green-100 text-green-800 border-green-300 px-4 py-2 rounded-full'
      case 'end':
        return 'bg-red-100 text-red-800 border-red-300 px-4 py-2 rounded-full'
      case 'service':
        return 'bg-blue-100 text-blue-800 border-blue-300 px-3 py-2 rounded-lg'
      case 'user':
        return 'bg-purple-100 text-purple-800 border-purple-300 px-3 py-2 rounded-lg'
      case 'gateway':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300 px-3 py-2 rounded-diamond'
      case 'arrow':
        return 'text-gray-500 font-mono text-lg'
      case 'branch':
        return 'text-gray-400 font-mono'
      default:
        return 'text-gray-600'
    }
  }

  const renderElement = (line: string, index: number) => {
    const type = getElementType(line)
    const trimmed = line.trim()
    
    // Extraer el nombre del elemento para mejor presentación
    let displayText = trimmed
    if (type === 'start' || type === 'end') {
      displayText = trimmed.split(':')[1]?.trim() || trimmed
    } else if (type === 'service' || type === 'user') {
      const parts = trimmed.split(':')
      if (parts.length > 1) {
        const taskName = parts[1].split('(')[0].trim()
        const actor = parts[1].split('(')[1]?.replace(')', '').trim()
        displayText = (
          <div className="text-center">
            <div className="font-semibold">{taskName}</div>
            {actor && <div className="text-xs opacity-75">({actor})</div>}
          </div>
        )
      }
    }

    return (
      <div key={index} className="flex items-center justify-center my-2">
        {type === 'arrow' ? (
          <div className={`${getElementStyle(type)} select-none`}>
            {trimmed}
          </div>
        ) : type === 'branch' ? (
          <div className={`${getElementStyle(type)} text-left w-full pl-4`}>
            {trimmed}
          </div>
        ) : (
          <div className={`${getElementStyle(type)} border-2 inline-block max-w-xs text-center shadow-sm`}>
            {displayText}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="bg-gray-50 p-6 rounded-lg overflow-x-auto">
      <div className="font-mono text-sm space-y-1 min-w-max">
        {lines.map((line, index) => renderElement(line, index))}
      </div>
      
      <div className="mt-4 pt-4 border-t border-gray-200">
        <h4 className="font-semibold text-sm text-gray-600 mb-2">Leyenda:</h4>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-green-100 border border-green-300 rounded-full"></div>
            <span>Inicio</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-red-100 border border-red-300 rounded-full"></div>
            <span>Fin</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-blue-100 border border-blue-300 rounded"></div>
            <span>Tarea Sistema</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-purple-100 border border-purple-300 rounded"></div>
            <span>Tarea Usuario</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-yellow-100 border border-yellow-300 rounded"></div>
            <span>Decisión</span>
          </div>
        </div>
      </div>
    </div>
  )
}