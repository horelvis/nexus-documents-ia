import { json, redirect, type ActionFunctionArgs, type LoaderFunctionArgs } from '@remix-run/node';
import { useLoaderData, Form, useNavigation, useSearchParams, Link } from '@remix-run/react';
import { useState } from 'react';
import { ArrowLeft, Bot, Save, AlertCircle } from 'lucide-react';
import { Button } from '~/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '~/components/ui/card';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { Textarea } from '~/components/ui/textarea';
import { Checkbox } from '~/components/ui/checkbox';
import { Badge } from '~/components/ui/badge';
import { Alert, AlertDescription } from '~/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';

interface Tool {
  name: string;
  description: string;
  tool_type: string;
  requires_admin: boolean;
}

interface AgentType {
  id: string;
  name: string;
  description: string;
  icon: string;
  default_tools: string[];
  configuration_schema: any;
}

export async function loader({ request }: LoaderFunctionArgs) {
  // TODO: Fetch available tools and agent types from API
  const tools: Tool[] = [
    {
      name: 'create_signature_request',
      description: 'Crear una nueva solicitud de firma digital',
      tool_type: 'internal',
      requires_admin: false
    },
    {
      name: 'get_signature_status',
      description: 'Consultar el estado de una solicitud de firma',
      tool_type: 'internal',
      requires_admin: false
    },
    {
      name: 'list_signature_requests',
      description: 'Listar solicitudes de firma del usuario',
      tool_type: 'internal',
      requires_admin: false
    },
    {
      name: 'search_documents',
      description: 'Buscar documentos usando búsqueda semántica',
      tool_type: 'internal',
      requires_admin: false
    },
    {
      name: 'analyze_document',
      description: 'Analizar contenido de documentos con IA',
      tool_type: 'internal',
      requires_admin: false
    },
    {
      name: 'calculate',
      description: 'Realizar cálculos matemáticos básicos',
      tool_type: 'internal',
      requires_admin: false
    }
  ];

  const agentTypes: AgentType[] = [
    {
      id: 'digital_signature',
      name: 'Agente de Firma Digital',
      description: 'Especializado en gestión de solicitudes de firma electrónica',
      icon: '📝',
      default_tools: ['create_signature_request', 'get_signature_status', 'list_signature_requests', 'search_documents'],
      configuration_schema: {
        default_signature_type: { type: 'select', options: ['sequential', 'parallel'] },
        notification_settings: { type: 'object' },
        security_level: { type: 'select', options: ['standard', 'high'] }
      }
    },
    {
      id: 'document_analyzer',
      name: 'Analizador de Documentos',
      description: 'Análisis inteligente de documentos y extracción de información',
      icon: '🔍',
      default_tools: ['analyze_document', 'search_documents', 'calculate'],
      configuration_schema: {
        analysis_types: { type: 'multiselect', options: ['summary', 'keywords', 'sentiment', 'general'] },
        confidence_threshold: { type: 'number', min: 0, max: 1 },
        language_settings: { type: 'object' }
      }
    },
    {
      id: 'custom',
      name: 'Agente Personalizado',
      description: 'Agente genérico con herramientas personalizables',
      icon: '⚙️',
      default_tools: ['search_documents', 'calculate'],
      configuration_schema: {}
    }
  ];

  return json({ tools, agentTypes });
}

export async function action({ request }: ActionFunctionArgs) {
  const formData = await request.formData();
  
  const agentData = {
    name: formData.get('name'),
    description: formData.get('description'),
    type: formData.get('type'),
    is_public: formData.get('is_public') === 'on',
    tools: formData.getAll('tools'),
    configuration: JSON.parse(formData.get('configuration') as string || '{}')
  };

  // TODO: Call API to create agent
  console.log('Creating agent:', agentData);

  // For now, redirect back to agents list
  return redirect('/dashboard/agents');
}

export default function NewAgent() {
  const { tools, agentTypes } = useLoaderData<typeof loader>();
  const navigation = useNavigation();
  const [searchParams] = useSearchParams();
  const preselectedType = searchParams.get('type');

  const [selectedType, setSelectedType] = useState(preselectedType || '');
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [configuration, setConfiguration] = useState<Record<string, any>>({});

  const selectedAgentType = agentTypes.find(type => type.id === selectedType);

  // Update tools when agent type changes
  const handleTypeChange = (type: string) => {
    setSelectedType(type);
    const agentType = agentTypes.find(t => t.id === type);
    if (agentType) {
      setSelectedTools(agentType.default_tools);
      setConfiguration({});
    }
  };

  const handleToolToggle = (toolName: string) => {
    setSelectedTools(prev => 
      prev.includes(toolName)
        ? prev.filter(t => t !== toolName)
        : [...prev, toolName]
    );
  };

  const isSubmitting = navigation.state === 'submitting';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center space-x-4">
        <Link to="/dashboard/agents">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Volver
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Crear Nuevo Agente</h1>
          <p className="text-muted-foreground">
            Configura un nuevo asistente de inteligencia artificial
          </p>
        </div>
      </div>

      <Form method="post" className="space-y-6">
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Basic Information */}
          <Card>
            <CardHeader>
              <CardTitle>Información Básica</CardTitle>
              <CardDescription>
                Configuración general del agente
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Nombre del Agente</Label>
                <Input
                  id="name"
                  name="name"
                  placeholder="Ej: Asistente de Contratos"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Descripción</Label>
                <Textarea
                  id="description"
                  name="description"
                  placeholder="Describe las funciones y capacidades del agente"
                  rows={3}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="type">Tipo de Agente</Label>
                <Select 
                  name="type" 
                  value={selectedType} 
                  onValueChange={handleTypeChange}
                  required
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecciona un tipo" />
                  </SelectTrigger>
                  <SelectContent>
                    {agentTypes.map((type) => (
                      <SelectItem key={type.id} value={type.id}>
                        <div className="flex items-center space-x-2">
                          <span>{type.icon}</span>
                          <span>{type.name}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {selectedAgentType && (
                <Alert>
                  <Bot className="h-4 w-4" />
                  <AlertDescription>
                    {selectedAgentType.description}
                  </AlertDescription>
                </Alert>
              )}

              <div className="flex items-center space-x-2">
                <Checkbox id="is_public" name="is_public" />
                <Label htmlFor="is_public" className="text-sm">
                  Hacer público (otros usuarios pueden usar este agente)
                </Label>
              </div>
            </CardContent>
          </Card>

          {/* Tools Selection */}
          <Card>
            <CardHeader>
              <CardTitle>Herramientas Disponibles</CardTitle>
              <CardDescription>
                Selecciona las herramientas que puede usar el agente
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {tools.map((tool) => (
                  <div key={tool.name} className="flex items-start space-x-3">
                    <Checkbox
                      id={tool.name}
                      checked={selectedTools.includes(tool.name)}
                      onCheckedChange={() => handleToolToggle(tool.name)}
                    />
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center space-x-2">
                        <Label htmlFor={tool.name} className="text-sm font-medium">
                          {tool.name.replace(/_/g, ' ')}
                        </Label>
                        <Badge variant="outline" className="text-xs">
                          {tool.tool_type}
                        </Badge>
                        {tool.requires_admin && (
                          <Badge variant="destructive" className="text-xs">
                            Admin
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {tool.description}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Hidden inputs for selected tools */}
              {selectedTools.map((tool) => (
                <input key={tool} type="hidden" name="tools" value={tool} />
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Configuration */}
        {selectedAgentType && Object.keys(selectedAgentType.configuration_schema).length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Configuración Avanzada</CardTitle>
              <CardDescription>
                Parámetros específicos para este tipo de agente
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-2">
                {Object.entries(selectedAgentType.configuration_schema).map(([key, schema]: [string, any]) => (
                  <div key={key} className="space-y-2">
                    <Label htmlFor={`config-${key}`}>
                      {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </Label>
                    {schema.type === 'select' && (
                      <Select 
                        onValueChange={(value) => 
                          setConfiguration(prev => ({ ...prev, [key]: value }))
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Seleccionar..." />
                        </SelectTrigger>
                        <SelectContent>
                          {schema.options.map((option: string) => (
                            <SelectItem key={option} value={option}>
                              {option}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                    {schema.type === 'number' && (
                      <Input
                        id={`config-${key}`}
                        type="number"
                        min={schema.min}
                        max={schema.max}
                        step={0.1}
                        onChange={(e) =>
                          setConfiguration(prev => ({ ...prev, [key]: parseFloat(e.target.value) }))
                        }
                      />
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Hidden configuration input */}
        <input type="hidden" name="configuration" value={JSON.stringify(configuration)} />

        {/* Actions */}
        <div className="flex items-center justify-end space-x-4">
          <Link to="/dashboard/agents">
            <Button variant="outline" type="button">
              Cancelar
            </Button>
          </Link>
          <Button type="submit" disabled={isSubmitting || !selectedType}>
            {isSubmitting ? (
              <>
                <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-background border-t-foreground" />
                Creando...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Crear Agente
              </>
            )}
          </Button>
        </div>
      </Form>
    </div>
  );
}