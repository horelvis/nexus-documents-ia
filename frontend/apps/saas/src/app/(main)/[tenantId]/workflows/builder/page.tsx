"use client"

import { useState, use } from "react"
import { useWorkflowsService } from "@/lib/services/workflows.service"
import { 
  IconRobot, 
  IconWand,
  IconCode,
  IconFileText,
  IconBrain,
  IconChevronRight,
  IconPlus,
  IconSettings,
  IconEye,
  IconAlertTriangle,
  IconCircleCheck,
  IconClockPlay,
  IconDownload,
  IconGitBranch,
  IconRefresh
} from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Separator } from "@/components/ui/separator"
import { BPMNGenerationResult } from "@/lib/services/workflows.service"
import { BPMNVisualizer } from "@/components/workflows/BPMNVisualizer"
import { BPMNDisplay as BPMNEditor } from "@/components/workflows/BPMNDisplay"
import { convertTextBpmnToXml } from "@/lib/bpmn-utils"

export default function ProcessBuilderPage({ params }: { params: Promise<{ tenantId: string }> }) {
  const resolvedParams = use(params)
  const workflowsService = useWorkflowsService()
  const [processDescription, setProcessDescription] = useState("")
  const [processType, setProcessType] = useState("general")
  const [duration, setDuration] = useState("auto")
  const [automationLevel, setAutomationLevel] = useState("balanced")
  const [stakeholders, setStakeholders] = useState("")
  const [additionalContext, setAdditionalContext] = useState("")
  const [isGenerating, setIsGenerating] = useState(false)
  const [activeTab, setActiveTab] = useState("describe")
  const [generatedProcess, setGeneratedProcess] = useState<BPMNGenerationResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const processTypes = [
    { value: "contract_renewal", label: "Renovación de Contratos", description: "Proceso para renovar contratos laborales" },
    { value: "contract_termination", label: "Terminación de Contratos", description: "Proceso para terminar contratos" },
    { value: "onboarding", label: "Onboarding", description: "Incorporación de nuevos empleados" },
    { value: "disciplinary", label: "Proceso Disciplinario", description: "Gestión de medidas disciplinarias" },
    { value: "performance_review", label: "Evaluación de Desempeño", description: "Proceso de evaluación periódica" },
    { value: "leave_request", label: "Solicitud de Permisos", description: "Gestión de solicitudes de ausencias" },
    { value: "general", label: "Proceso General", description: "Proceso personalizado" }
  ]

  const examplePrompts = [
    "Crear un proceso para gestionar solicitudes de vacaciones que incluya aprobación del manager y notificación a RRHH",
    "Proceso disciplinario que cumpla con la normativa española, con derecho a alegaciones y posible sanción",
    "Workflow para promociones internas con evaluación de competencias y aprobación en cascada",
    "Proceso de incorporación que incluya documentación, asignación de equipos y formación inicial"
  ]

  const handleGenerateProcess = async () => {
    if (!processDescription.trim()) {
      alert("Por favor describe el proceso que quieres crear")
      return
    }

    setIsGenerating(true)
    setError(null)
    
    try {
      const response = await workflowsService.generateBPMN({
        process_description: processDescription,
        tenant_id: resolvedParams.tenantId,
        process_type: processType,
        context: {
          duration: duration,
          automation_level: automationLevel,
          stakeholders: stakeholders.split(',').map(s => s.trim()).filter(Boolean),
          additional_context: additionalContext
        }
      })
      
      // El apiClient envuelve la respuesta en {data: ..., status: ...}
      const result = response.data || response
      console.log('🔍 Response:', response)
      console.log('🔍 Result:', result)
      console.log('✅ result.success:', result.success)
      console.log('📝 result.data:', result.data)
      
      setGeneratedProcess(result)
      setActiveTab("preview")
    } catch (error) {
      console.error('Error generating process:', error)
      setError('Error al generar el proceso. Intenta de nuevo.')
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <div className="container mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <IconWand className="h-8 w-8 text-cyan-600" />
            Process Builder
          </h1>
          <p className="text-muted-foreground mt-1">
            Crea workflows personalizados usando inteligencia artificial
          </p>
        </div>
        <Badge className="bg-gradient-to-r from-cyan-100 to-blue-100 text-cyan-800 px-3 py-1">
          <IconBrain className="h-4 w-4 mr-1" />
          AI-Powered
        </Badge>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="describe">✍️ Describir Proceso</TabsTrigger>
          <TabsTrigger value="preview">👀 Preview</TabsTrigger>
          <TabsTrigger value="configure">⚙️ Configurar</TabsTrigger>
        </TabsList>

        <TabsContent value="describe" className="space-y-6">
          {/* How it works */}
          <Alert>
            <IconRobot className="h-4 w-4" />
            <AlertDescription>
              Describe tu proceso en lenguaje natural. La IA analizará tu descripción y generará 
              automáticamente el workflow BPMN optimizado con validación legal.
            </AlertDescription>
          </Alert>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Main Form */}
            <div className="lg:col-span-2 space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Describe tu Proceso</CardTitle>
                  <CardDescription>
                    Explica paso a paso cómo debería funcionar tu proceso
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="processType">Tipo de Proceso</Label>
                    <Select value={processType} onValueChange={setProcessType}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {processTypes.map((type) => (
                          <SelectItem key={type.value} value={type.value}>
                            <div>
                              <div className="font-medium">{type.label}</div>
                              <div className="text-xs text-muted-foreground">{type.description}</div>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="description">Descripción del Proceso</Label>
                    <Textarea
                      id="description"
                      placeholder="Ej: Necesito un proceso para gestionar solicitudes de vacaciones. Debe incluir: 1) El empleado solicita las fechas, 2) El manager revisa y aprueba/rechaza, 3) Si se aprueba, RRHH es notificado automáticamente, 4) Se actualiza el calendario del equipo..."
                      className="min-h-[150px]"
                      value={processDescription}
                      onChange={(e) => setProcessDescription(e.target.value)}
                    />
                    <p className="text-xs text-muted-foreground">
                      Sé lo más específico posible. Incluye roles, condiciones de decisión, y acciones requeridas.
                    </p>
                  </div>

                  <div className="flex gap-3">
                    <Button 
                      onClick={handleGenerateProcess}
                      disabled={isGenerating || !processDescription.trim()}
                      className="flex-1"
                    >
                      {isGenerating ? (
                        <>
                          <IconRobot className="h-4 w-4 mr-2 animate-bounce" />
                          Generando con IA...
                        </>
                      ) : (
                        <>
                          <IconWand className="h-4 w-4 mr-2" />
                          Generar Proceso
                        </>
                      )}
                    </Button>
                    
                    <Button 
                      onClick={async () => {
                        setIsGenerating(true)
                        setError(null)
                        setActiveTab("preview")
                        try {
                          console.log('🚀 Iniciando demo...')
                          const response = await workflowsService.demoContractRenewal(true)
                          console.log('🔍 Response RAW:', response)
                          
                          // El apiClient envuelve la respuesta en {data: ..., status: ...}
                          const result = response.data || response
                          console.log('🔍 Actual result:', result)
                          console.log('🔍 Result success:', result?.success)
                          console.log('🔍 Result bpmn_generation:', result?.bpmn_generation)
                          
                          // Mapear la estructura del demo a la estructura esperada
                          if (result && result.success && result.bpmn_generation) {
                            const mappedResult = {
                              success: true,
                              message: result.message,
                              data: result.bpmn_generation,
                              performance_note: result.performance_note,
                              architecture_note: result.architecture_note
                            }
                            console.log('📋 Mapped result:', mappedResult)
                            setGeneratedProcess(mappedResult)
                          } else {
                            console.log('⚠️ Setting result directly:', result)
                            setGeneratedProcess(result)
                          }
                        } catch (error) {
                          console.error('❌ Demo error:', error)
                          console.error('❌ Error stack:', error.stack)
                          setError(`Error en demo: ${error.message}`)
                        } finally {
                          setIsGenerating(false)
                        }
                      }}
                      disabled={isGenerating}
                      variant="outline"
                      className="flex-1"
                    >
                      {isGenerating ? (
                        <IconRefresh className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <IconRobot className="h-4 w-4 mr-2" />
                      )}
                      Demo Rápido
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Advanced Options */}
              <Card>
                <CardHeader>
                  <CardTitle>Opciones Avanzadas</CardTitle>
                  <CardDescription>
                    Configuración adicional para personalizar la generación
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Duración Estimada</Label>
                      <Select value={duration} onValueChange={setDuration}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="auto">Automática</SelectItem>
                          <SelectItem value="1-3">1-3 días</SelectItem>
                          <SelectItem value="1-2-weeks">1-2 semanas</SelectItem>
                          <SelectItem value="1-month">1 mes</SelectItem>
                          <SelectItem value="custom">Personalizada</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label>Nivel de Automatización</Label>
                      <Select value={automationLevel} onValueChange={setAutomationLevel}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="minimal">Mínima</SelectItem>
                          <SelectItem value="balanced">Equilibrada</SelectItem>
                          <SelectItem value="high">Alta</SelectItem>
                          <SelectItem value="full">Máxima</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label>Stakeholders Involucrados</Label>
                    <Input 
                      placeholder="Ej: RRHH, Manager, Empleado, Legal, IT..." 
                      value={stakeholders}
                      onChange={(e) => setStakeholders(e.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label>Contexto Adicional</Label>
                    <Textarea 
                      placeholder="Información adicional sobre tu organización, políticas específicas, o restricciones..."
                      className="min-h-[80px]"
                      value={additionalContext}
                      onChange={(e) => setAdditionalContext(e.target.value)}
                    />
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Sidebar */}
            <div className="space-y-4">
              {/* Examples */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">💡 Ejemplos</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {examplePrompts.map((example, idx) => (
                    <div key={idx}>
                      <button
                        onClick={() => setProcessDescription(example)}
                        className="text-left text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer p-2 hover:bg-accent rounded"
                      >
                        {example}
                      </button>
                      {idx < examplePrompts.length - 1 && <Separator className="mt-2" />}
                    </div>
                  ))}
                </CardContent>
              </Card>

              {/* Tips */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">📝 Consejos</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="space-y-2 text-sm text-muted-foreground">
                    <p>• <strong>Sé específico</strong> con los roles y responsabilidades</p>
                    <p>• <strong>Incluye condiciones</strong> de decisión claras</p>
                    <p>• <strong>Menciona plazos</strong> y deadlines importantes</p>
                    <p>• <strong>Especifica integraciones</strong> con otros sistemas</p>
                    <p>• <strong>Considera la normativa</strong> legal aplicable</p>
                  </div>
                </CardContent>
              </Card>

              {/* Features */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">🚀 Características</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="space-y-1 text-sm">
                    <div className="flex items-center gap-2">
                      <IconBrain className="h-4 w-4 text-purple-500" />
                      <span>Generación automática BPMN</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <IconSettings className="h-4 w-4 text-blue-500" />
                      <span>Validación legal Emma AI</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <IconFileText className="h-4 w-4 text-green-500" />
                      <span>Documentación automática</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <IconCode className="h-4 w-4 text-orange-500" />
                      <span>Exportación estándar</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="preview" className="space-y-6">
          {!generatedProcess ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-20">
                <IconEye className="h-16 w-16 text-gray-300 mb-4" />
                <p className="text-gray-500 mb-4">Preview del proceso aparecerá aquí</p>
                <p className="text-sm text-muted-foreground text-center">
                  Genera un proceso desde la pestaña "Describir Proceso" para ver el preview
                </p>
              </CardContent>
            </Card>
          ) : !generatedProcess.success ? (
            <Alert>
              <IconAlertTriangle className="h-4 w-4" />
              <AlertDescription>
                {generatedProcess.message}
              </AlertDescription>
            </Alert>
          ) : (
            <>
              {/* Process Description */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <IconFileText className="h-5 w-5" />
                    Descripción del Proceso
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <pre className="whitespace-pre-wrap text-sm text-gray-700">
                      {generatedProcess.data?.process_description}
                    </pre>
                  </div>
                </CardContent>
              </Card>

              {/* BPMN Diagram */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <IconGitBranch className="h-5 w-5" />
                    Diagrama BPMN Generado
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Tabs defaultValue="visual" className="w-full">
                    <TabsList className="grid w-full grid-cols-3">
                      <TabsTrigger value="visual">Vista Rápida</TabsTrigger>
                      <TabsTrigger value="editor">Editor Completo</TabsTrigger>
                      <TabsTrigger value="code">Código BPMN</TabsTrigger>
                    </TabsList>
                    
                    <TabsContent value="visual" className="mt-4">
                      <BPMNVisualizer bpmnText={generatedProcess.data?.bpmn_generation?.generated_bpmn || ""} />
                    </TabsContent>
                    
                    <TabsContent value="editor" className="mt-4">
                      <BPMNEditor 
                        initialBpmn={(() => {
                          const rawBpmn = generatedProcess.data?.bpmn_generation?.generated_bpmn || ""
                          console.log('🔧 BPMNEditor - Raw BPMN data:', {
                            generatedProcessData: generatedProcess.data,
                            bpmnGeneration: generatedProcess.data?.bpmn_generation,
                            generatedBpmn: rawBpmn,
                            rawBpmnLength: rawBpmn.length
                          })
                          return convertTextBpmnToXml(rawBpmn)
                        })()}
                        height="600px"
                      />
                    </TabsContent>
                    
                    <TabsContent value="code" className="mt-4">
                      <div className="bg-gray-50 p-4 rounded-lg">
                        <h4 className="font-semibold mb-2">Proceso Original (IA)</h4>
                        <pre className="bg-blue-50 p-4 rounded text-xs overflow-auto max-h-48 mb-4">
                          <code>{generatedProcess.data?.bpmn_generation?.generated_bpmn || ""}</code>
                        </pre>
                        <h4 className="font-semibold mb-2">XML BPMN Convertido</h4>
                        <pre className="bg-black text-green-400 p-4 rounded text-xs overflow-auto max-h-96">
                          <code>{convertTextBpmnToXml(generatedProcess.data?.bpmn_generation?.generated_bpmn || "")}</code>
                        </pre>
                      </div>
                    </TabsContent>
                  </Tabs>
                </CardContent>
              </Card>

              {/* Extracted Elements */}
              {generatedProcess.data?.bpmn_generation?.extracted_elements && (
                <Card>
                  <CardHeader>
                    <CardTitle>Elementos Extraídos</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                      {generatedProcess.data.bpmn_generation?.extracted_elements?.agents && (
                        <div>
                          <h4 className="font-semibold mb-2">👥 Agentes</h4>
                          <ul className="space-y-1 text-sm">
                            {generatedProcess.data.bpmn_generation?.extracted_elements?.agents?.map((agent: any, idx: number) => (
                              <li key={idx} className="flex justify-between">
                                <span>{agent.name}</span>
                                <Badge variant="secondary" className="text-xs">
                                  {Math.round(agent.confidence * 100)}%
                                </Badge>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {generatedProcess.data.bpmn_generation?.extracted_elements?.tasks && (
                        <div>
                          <h4 className="font-semibold mb-2">📋 Tareas</h4>
                          <ul className="space-y-1 text-sm">
                            {generatedProcess.data.bpmn_generation?.extracted_elements?.tasks?.map((task: any, idx: number) => (
                              <li key={idx} className="text-sm">
                                <div className="truncate">{task.description}</div>
                                <Badge variant="secondary" className="text-xs">
                                  {Math.round(task.confidence * 100)}%
                                </Badge>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {generatedProcess.data.bpmn_generation?.extracted_elements?.conditions && (
                        <div>
                          <h4 className="font-semibold mb-2">❓ Condiciones</h4>
                          <ul className="space-y-1 text-sm">
                            {generatedProcess.data.bpmn_generation?.extracted_elements?.conditions?.map((condition: any, idx: number) => (
                              <li key={idx} className="text-sm">
                                <div className="truncate">{condition.condition}</div>
                                <Badge variant="secondary" className="text-xs">
                                  {Math.round(condition.confidence * 100)}%
                                </Badge>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {generatedProcess.data.bpmn_generation?.extracted_elements?.process_info && (
                        <div>
                          <h4 className="font-semibold mb-2">ℹ️ Info Proceso</h4>
                          <ul className="space-y-1 text-sm">
                            {generatedProcess.data.bpmn_generation?.extracted_elements?.process_info?.map((info: any, idx: number) => (
                              <li key={idx} className="text-sm">
                                <div className="truncate">{info.info}</div>
                                <Badge variant="secondary" className="text-xs">
                                  {Math.round(info.confidence * 100)}%
                                </Badge>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="configure" className="space-y-6">
          {!generatedProcess?.success ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-20">
                <IconSettings className="h-16 w-16 text-gray-300 mb-4" />
                <p className="text-gray-500 mb-4">Configuración del proceso</p>
                <p className="text-sm text-muted-foreground text-center">
                  Genera y previsualiza un proceso para acceder a las opciones de configuración
                </p>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Legal Validation */}
              {generatedProcess.data?.validated_bpmn && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <IconCircleCheck className="h-5 w-5 text-green-600" />
                      Validación Legal (Emma AI)
                      <Badge className="bg-green-100 text-green-800">
                        Confianza: {Math.round((generatedProcess.data.bpmn_generation?.validated_bpmn?.emma_confidence || 0) * 100)}%
                      </Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {/* Compliance Points */}
                      <div>
                        <h4 className="font-semibold text-green-700 mb-2">✅ Cumplimiento Legal</h4>
                        <ul className="space-y-1 text-sm">
                          {generatedProcess.data.bpmn_generation?.validated_bpmn?.legal_compliance_points?.map((point: string, idx: number) => (
                            <li key={idx} className="text-green-600">{point}</li>
                          ))}
                        </ul>
                      </div>

                      {/* Recommendations */}
                      <div>
                        <h4 className="font-semibold text-blue-700 mb-2">💡 Recomendaciones</h4>
                        <ul className="space-y-1 text-sm">
                          {generatedProcess.data.bpmn_generation?.validated_bpmn?.recommendations?.map((rec: string, idx: number) => (
                            <li key={idx} className="text-blue-600">• {rec}</li>
                          ))}
                        </ul>
                      </div>

                      {/* Risks */}
                      <div>
                        <h4 className="font-semibold text-orange-700 mb-2">⚠️ Riesgos Identificados</h4>
                        <ul className="space-y-1 text-sm">
                          {generatedProcess.data.bpmn_generation?.validated_bpmn?.identified_risks?.map((risk: string, idx: number) => (
                            <li key={idx} className="text-orange-600">• {risk}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Execution Plan */}
              {generatedProcess.data?.execution_plan && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <IconClockPlay className="h-5 w-5" />
                      Plan de Ejecución
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      {/* Steps */}
                      <div>
                        <h4 className="font-semibold mb-3">Pasos de Ejecución</h4>
                        <div className="space-y-2">
                          {generatedProcess.data.bpmn_generation?.execution_plan?.execution_steps?.map((step: string, idx: number) => (
                            <div key={idx} className="flex items-center gap-2 p-2 border rounded">
                              <span className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs flex items-center justify-center font-semibold">
                                {idx + 1}
                              </span>
                              <span className="text-sm">{step}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Stakeholders & Timeline */}
                      <div className="space-y-4">
                        <div>
                          <h4 className="font-semibold mb-2">👥 Stakeholders</h4>
                          <div className="space-y-1">
                            {Object.entries(generatedProcess.data.bpmn_generation?.execution_plan?.stakeholders || {}).map(([role, desc]) => (
                              <div key={role} className="flex justify-between text-sm">
                                <span className="font-medium">{role}:</span>
                                <span className="text-muted-foreground">{desc as string}</span>
                              </div>
                            ))}
                          </div>
                        </div>

                        <div>
                          <h4 className="font-semibold mb-2">⏱️ Timeline</h4>
                          <Badge variant="secondary" className="text-sm">
                            Duración estimada: {generatedProcess.data.bpmn_generation?.execution_plan?.timeline?.total_duration}
                          </Badge>
                        </div>

                        <div>
                          <h4 className="font-semibold mb-2">🤖 Acciones Automatizadas</h4>
                          <ul className="text-xs space-y-1">
                            {generatedProcess.data.bpmn_generation?.execution_plan?.automated_actions?.map((action: string, idx: number) => (
                              <li key={idx} className="text-muted-foreground">• {action}</li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Process Configuration */}
              <Card>
                <CardHeader>
                  <CardTitle>Configuración del Proceso</CardTitle>
                  <CardDescription>
                    Personaliza los parámetros del proceso antes de guardarlo
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Nombre del Proceso</Label>
                      <Input 
                        defaultValue={generatedProcess.data?.process_description?.split('.')[0] || "Nuevo Proceso"}
                        placeholder="Nombre descriptivo del proceso"
                      />
                    </div>
                    
                    <div className="space-y-2">
                      <Label>Categoría</Label>
                      <Select defaultValue={processType}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="contract_renewal">Renovación de Contratos</SelectItem>
                          <SelectItem value="contract_termination">Terminación de Contratos</SelectItem>
                          <SelectItem value="onboarding">Onboarding</SelectItem>
                          <SelectItem value="disciplinary">Proceso Disciplinario</SelectItem>
                          <SelectItem value="performance_review">Evaluación de Desempeño</SelectItem>
                          <SelectItem value="leave_request">Solicitud de Permisos</SelectItem>
                          <SelectItem value="general">Proceso General</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label>Descripción</Label>
                    <Textarea 
                      defaultValue={generatedProcess.data?.process_description}
                      className="min-h-[100px]"
                      placeholder="Descripción detallada del proceso"
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Prioridad</Label>
                      <Select defaultValue="medium">
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="low">Baja</SelectItem>
                          <SelectItem value="medium">Media</SelectItem>
                          <SelectItem value="high">Alta</SelectItem>
                          <SelectItem value="urgent">Urgente</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    
                    <div className="space-y-2">
                      <Label>Estado</Label>
                      <Select defaultValue="draft">
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="draft">Borrador</SelectItem>
                          <SelectItem value="review">En Revisión</SelectItem>
                          <SelectItem value="active">Activo</SelectItem>
                          <SelectItem value="archived">Archivado</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Actions */}
              <Card>
                <CardContent className="flex gap-3 pt-6">
                  <Button className="flex-1">
                    <IconCircleCheck className="h-4 w-4 mr-2" />
                    Guardar Proceso
                  </Button>
                  <Button variant="outline">
                    <IconDownload className="h-4 w-4 mr-2" />
                    Exportar BPMN
                  </Button>
                  <Button variant="outline">
                    <IconFileText className="h-4 w-4 mr-2" />
                    Generar Reporte
                  </Button>
                  <Button variant="outline" onClick={() => setActiveTab("preview")}>
                    <IconEye className="h-4 w-4 mr-2" />
                    Ver Preview
                  </Button>
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}