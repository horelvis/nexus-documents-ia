/**
 * Utilidades para convertir entre formatos BPMN
 */

export function convertTextBpmnToXml(bpmnText: string): string {
  console.log('🔍 convertTextBpmnToXml called with:', {
    input: bpmnText,
    type: typeof bpmnText,
    length: bpmnText?.length,
    first100: bpmnText?.substring(0, 100)
  })

  if (!bpmnText || typeof bpmnText !== 'string' || bpmnText.trim() === '') {
    console.log('❌ Empty or invalid input, returning default BPMN')
    return getEmptyBpmnXml()
  }

  // If it's already XML, return as is
  if (bpmnText.trim().startsWith('<?xml') || bpmnText.includes('<bpmn')) {
    console.log('✅ Input is already XML, returning as-is')
    return bpmnText
  }

  try {
    console.log('🔍 Converting text BPMN to XML...')
    console.log('📝 Full text:', bpmnText)
    
    const lines = bpmnText.split('\n').filter(line => line.trim() !== '')
    console.log('📄 Lines found:', lines.length, lines)
    
    // Check if it's structured format (with START_EVENT, etc.) or natural text
    const hasStructuredFormat = lines.some(line => 
      line.includes('START_EVENT') || 
      line.includes('SERVICE_TASK') || 
      line.includes('USER_TASK') ||
      line.includes('END_EVENT')
    )
    
    if (!hasStructuredFormat) {
      console.log('🔄 No structured format found, converting natural text to BPMN')
      // Convert natural text to basic BPMN structure
      return generateBasicBpmnFromText(bpmnText)
    }
    
    console.log('✅ Structured format detected, using advanced parsing')
    
    // Extraer elementos del texto BPMN con mejor parsing (existing logic)
    const elements: any[] = []
    const flows: any[] = []
    let currentY = 150
    let currentX = 150
    let elementCounter = 1
    let inBranch = false
    let branchY = currentY
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      const trimmed = line.trim()
      
      // Skip arrows and branch indicators
      if (trimmed === '→' || trimmed.startsWith('├─') || trimmed.startsWith('└─') || 
          trimmed.startsWith('│') || trimmed === '') {
        
        // Handle branch positioning
        if (trimmed.startsWith('├─') || trimmed.startsWith('└─')) {
          inBranch = true
          branchY = currentY + 100
        }
        continue
      }
      
      let element: any = null
      
      if (trimmed.includes('START_EVENT')) {
        const name = trimmed.split(':')[1]?.trim() || 'Inicio'
        element = {
          type: 'startEvent',
          id: `StartEvent_${elementCounter++}`,
          name: name,
          x: currentX,
          y: currentY
        }
      } else if (trimmed.includes('END_EVENT')) {
        const name = trimmed.split(':')[1]?.trim() || 'Fin'
        element = {
          type: 'endEvent',
          id: `EndEvent_${elementCounter++}`,
          name: name,
          x: currentX,
          y: inBranch ? branchY : currentY
        }
      } else if (trimmed.includes('SERVICE_TASK')) {
        const parts = trimmed.split(':')
        const taskInfo = parts[1] || ''
        const taskName = taskInfo.split('(')[0]?.trim() || 'Tarea de Sistema'
        element = {
          type: 'serviceTask',
          id: `ServiceTask_${elementCounter++}`,
          name: taskName,
          x: currentX,
          y: inBranch ? branchY : currentY
        }
      } else if (trimmed.includes('USER_TASK')) {
        const parts = trimmed.split(':')
        const taskInfo = parts[1] || ''
        const taskName = taskInfo.split('(')[0]?.trim() || 'Tarea de Usuario'
        element = {
          type: 'userTask',
          id: `UserTask_${elementCounter++}`,
          name: taskName,
          x: currentX,
          y: inBranch ? branchY : currentY
        }
      } else if (trimmed.includes('EXCLUSIVE_GATEWAY')) {
        const name = trimmed.split(':')[1]?.trim() || 'Decisión'
        element = {
          type: 'exclusiveGateway',
          id: `ExclusiveGateway_${elementCounter++}`,
          name: name,
          x: currentX,
          y: currentY
        }
        // Reset branch after gateway
        inBranch = false
      }
      
      if (element) {
        elements.push(element)
        currentX += 200
        if (!inBranch) {
          currentY += 20
        }
      }
    }

    // Si no se encontraron elementos válidos, devolver BPMN básico
    if (elements.length === 0) {
      return getEmptyBpmnXml()
    }

    return generateBpmnXml(elements)
    
  } catch (error) {
    console.error('Error converting text to BPMN XML:', error)
    return getEmptyBpmnXml()
  }
}

function generateBpmnXml(elements: any[]): string {
  if (elements.length === 0) {
    return getEmptyBpmnXml()
  }

  // Generar elementos del proceso de forma más simple
  const processElements: string[] = []
  const sequenceFlows: string[] = []
  const diagramElements: string[] = []

  elements.forEach((element, index) => {
    const nextElement = elements[index + 1]
    
    // Generar elemento del proceso
    switch (element.type) {
      case 'startEvent':
        processElements.push(`    <bpmn2:startEvent id="${element.id}" name="${element.name}" />`)
        break
      case 'endEvent':
        processElements.push(`    <bpmn2:endEvent id="${element.id}" name="${element.name}" />`)
        break
      case 'serviceTask':
        processElements.push(`    <bpmn2:serviceTask id="${element.id}" name="${element.name}" />`)
        break
      case 'userTask':
        processElements.push(`    <bpmn2:userTask id="${element.id}" name="${element.name}" />`)
        break
      case 'exclusiveGateway':
        processElements.push(`    <bpmn2:exclusiveGateway id="${element.id}" name="${element.name}" />`)
        break
    }
    
    // Generar conexiones (sequence flows)
    if (nextElement) {
      sequenceFlows.push(`    <bpmn2:sequenceFlow id="Flow_${index + 1}" sourceRef="${element.id}" targetRef="${nextElement.id}" />`)
    }
    
    // Generar elementos del diagrama
    const width = element.type === 'exclusiveGateway' ? 50 : (element.type.includes('Event') ? 36 : 100)
    const height = element.type === 'exclusiveGateway' ? 50 : (element.type.includes('Event') ? 36 : 80)
    
    diagramElements.push(`      <bpmndi:BPMNShape id="Shape_${element.id}" bpmnElement="${element.id}">
        <dc:Bounds height="${height}" width="${width}" x="${element.x}" y="${element.y}"/>
      </bpmndi:BPMNShape>`)
  })

  // Generar sequence flow shapes
  elements.forEach((element, index) => {
    const nextElement = elements[index + 1]
    if (nextElement) {
      const startX = element.x + (element.type.includes('Event') ? 18 : 50)
      const startY = element.y + (element.type.includes('Event') ? 18 : 40)
      const endX = nextElement.x
      const endY = nextElement.y + (nextElement.type.includes('Event') ? 18 : 40)
      
      diagramElements.push(`      <bpmndi:BPMNEdge id="Edge_Flow_${index + 1}" bpmnElement="Flow_${index + 1}">
        <di:waypoint x="${startX}" y="${startY}" />
        <di:waypoint x="${endX}" y="${endY}" />
      </bpmndi:BPMNEdge>`)
    }
  })

  return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn2:definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
                   xmlns:bpmn2="http://www.omg.org/spec/BPMN/20100524/MODEL" 
                   xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" 
                   xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" 
                   xmlns:di="http://www.omg.org/spec/DD/20100524/DI" 
                   xsi:schemaLocation="http://www.omg.org/spec/BPMN/20100524/MODEL BPMN20.xsd" 
                   id="Definitions_1" 
                   targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn2:process id="Process_1" isExecutable="false">
${processElements.join('\n')}
${sequenceFlows.join('\n')}
  </bpmn2:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_1">
${diagramElements.join('\n')}
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn2:definitions>`
}

function generateBasicBpmnFromText(text: string): string {
  console.log('🔧 Generating basic BPMN from natural text')
  
  // Extract key steps from natural text
  const lines = text.split('\n').filter(line => line.trim() !== '')
  const elements: any[] = []
  let elementCounter = 1
  let currentX = 150
  const currentY = 150
  
  // Always start with a start event
  elements.push({
    type: 'startEvent',
    id: `StartEvent_${elementCounter++}`,
    name: 'Inicio del Proceso',
    x: currentX,
    y: currentY
  })
  currentX += 200
  
  // Look for steps, tasks, or activities in the text
  const stepPattern = /(\d+[\.\)]?\s*(.+))/g
  const steps = []
  let match
  
  while ((match = stepPattern.exec(text)) !== null) {
    const stepText = match[2]?.trim()
    if (stepText && stepText.length > 5) {
      steps.push(stepText)
    }
  }
  
  // If no numbered steps found, look for common task indicators
  if (steps.length === 0) {
    const taskIndicators = [
      /revisar?\s+(.+)/gi,
      /evaluar?\s+(.+)/gi,
      /generar?\s+(.+)/gi,
      /notificar?\s+(.+)/gi,
      /decidir?\s+(.+)/gi,
      /aprobar?\s+(.+)/gi,
      /rechazar?\s+(.+)/gi,
      /documentar?\s+(.+)/gi
    ]
    
    for (const line of lines) {
      for (const pattern of taskIndicators) {
        const match = pattern.exec(line)
        if (match) {
          steps.push(match[0])
          pattern.lastIndex = 0 // Reset regex
        }
      }
    }
  }
  
  // Create tasks for each step
  for (const step of steps.slice(0, 5)) { // Limit to 5 steps to avoid clutter
    const taskType = step.toLowerCase().includes('revisar') || step.toLowerCase().includes('evaluar') ? 'userTask' : 'serviceTask'
    
    elements.push({
      type: taskType,
      id: `${taskType === 'userTask' ? 'UserTask' : 'ServiceTask'}_${elementCounter++}`,
      name: step.length > 50 ? step.substring(0, 47) + '...' : step,
      x: currentX,
      y: currentY
    })
    currentX += 200
  }
  
  // Always end with an end event
  elements.push({
    type: 'endEvent',
    id: `EndEvent_${elementCounter++}`,
    name: 'Fin del Proceso',
    x: currentX,
    y: currentY
  })
  
  console.log(`✅ Generated ${elements.length} BPMN elements from text`)
  return generateBpmnXml(elements)
}

function getEmptyBpmnXml(): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn2:definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
                   xmlns:bpmn2="http://www.omg.org/spec/BPMN/20100524/MODEL" 
                   xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" 
                   xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" 
                   xmlns:di="http://www.omg.org/spec/DD/20100524/DI" 
                   xsi:schemaLocation="http://www.omg.org/spec/BPMN/20100524/MODEL BPMN20.xsd" 
                   id="Definitions_1" 
                   targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn2:process id="Process_1" isExecutable="false">
    <bpmn2:startEvent id="StartEvent_1"/>
  </bpmn2:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_1">
      <bpmndi:BPMNShape id="_BPMNShape_StartEvent_2" bpmnElement="StartEvent_1">
        <dc:Bounds height="36.0" width="36.0" x="412.0" y="240.0"/>
      </bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn2:definitions>`
}