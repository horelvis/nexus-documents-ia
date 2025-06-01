import { json, type LoaderFunctionArgs } from '@remix-run/node';
import { useLoaderData, Link, Form, useNavigation } from '@remix-run/react';
import { Plus, Bot, MessageCircle, Zap, Settings, Trash2, Eye } from 'lucide-react';
import { Button } from '~/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '~/components/ui/card';
import { Badge } from '~/components/ui/badge';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '~/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '~/components/ui/dropdown-menu';

interface Agent {
  id: string;
  name: string;
  description: string;
  type: string;
  is_active: boolean;
  is_public: boolean;
  created_at: string;
  updated_at: string;
  created_by: string;
}

interface AgentStats {
  total_conversations: number;
  total_messages: number;
  total_executions: number;
  success_rate: number;
  last_used_at: string | null;
}

export async function loader({ request }: LoaderFunctionArgs) {
  // TODO: Implement API calls to fetch agents
  const mockAgents: Agent[] = [
    {
      id: '1',
      name: 'Asistente de Firma Digital',
      description: 'Agente especializado en la gestión de solicitudes de firma digital',
      type: 'digital_signature',
      is_active: true,
      is_public: true,
      created_at: '2024-01-06T10:00:00Z',
      updated_at: '2024-01-06T10:00:00Z',
      created_by: 'user-1'
    },
    {
      id: '2',
      name: 'Analizador de Documentos IA',
      description: 'Agente inteligente para análisis de documentos y extracción de información',
      type: 'document_analyzer',
      is_active: true,
      is_public: true,
      created_at: '2024-01-06T11:00:00Z',
      updated_at: '2024-01-06T11:00:00Z',
      created_by: 'user-1'
    }
  ];

  return json({ agents: mockAgents });
}

export default function AgentsIndex() {
  const { agents } = useLoaderData<typeof loader>();
  const navigation = useNavigation();

  const getAgentTypeColor = (type: string) => {
    switch (type) {
      case 'digital_signature':
        return 'bg-blue-100 text-blue-800';
      case 'document_analyzer':
        return 'bg-green-100 text-green-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getAgentTypeIcon = (type: string) => {
    switch (type) {
      case 'digital_signature':
        return '📝';
      case 'document_analyzer':
        return '🔍';
      default:
        return '🤖';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Agentes IA</h1>
          <p className="text-muted-foreground">
            Gestiona y configura tus asistentes de inteligencia artificial
          </p>
        </div>
        <Link to="new">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            Crear Agente
          </Button>
        </Link>
      </div>

      {/* Statistics Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Agentes</CardTitle>
            <Bot className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{agents.length}</div>
            <p className="text-xs text-muted-foreground">
              {agents.filter(a => a.is_active).length} activos
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Conversaciones</CardTitle>
            <MessageCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">1,234</div>
            <p className="text-xs text-muted-foreground">
              +12% desde el mes pasado
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ejecuciones</CardTitle>
            <Zap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">5,678</div>
            <p className="text-xs text-muted-foreground">
              +25% desde el mes pasado
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Tasa de Éxito</CardTitle>
            <Settings className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">94.2%</div>
            <p className="text-xs text-muted-foreground">
              +2.1% desde el mes pasado
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Agents Table */}
      <Card>
        <CardHeader>
          <CardTitle>Agentes Disponibles</CardTitle>
          <CardDescription>
            Lista de todos los agentes configurados en tu organización
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Agente</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Visibilidad</TableHead>
                <TableHead>Última Actualización</TableHead>
                <TableHead className="text-right">Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {agents.map((agent) => (
                <TableRow key={agent.id}>
                  <TableCell>
                    <div className="flex items-center space-x-3">
                      <div className="text-2xl">{getAgentTypeIcon(agent.type)}</div>
                      <div>
                        <div className="font-medium">{agent.name}</div>
                        <div className="text-sm text-muted-foreground line-clamp-1">
                          {agent.description}
                        </div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge className={getAgentTypeColor(agent.type)}>
                      {agent.type.replace('_', ' ')}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={agent.is_active ? 'default' : 'secondary'}>
                      {agent.is_active ? 'Activo' : 'Inactivo'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={agent.is_public ? 'outline' : 'secondary'}>
                      {agent.is_public ? 'Público' : 'Privado'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <time dateTime={agent.updated_at}>
                      {new Date(agent.updated_at).toLocaleDateString('es-ES')}
                    </time>
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" className="h-8 w-8 p-0">
                          <span className="sr-only">Abrir menú</span>
                          <Settings className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuLabel>Acciones</DropdownMenuLabel>
                        <DropdownMenuItem asChild>
                          <Link to={`${agent.id}`}>
                            <Eye className="mr-2 h-4 w-4" />
                            Ver Detalles
                          </Link>
                        </DropdownMenuItem>
                        <DropdownMenuItem asChild>
                          <Link to={`${agent.id}/chat`}>
                            <MessageCircle className="mr-2 h-4 w-4" />
                            Iniciar Chat
                          </Link>
                        </DropdownMenuItem>
                        <DropdownMenuItem asChild>
                          <Link to={`${agent.id}/edit`}>
                            <Settings className="mr-2 h-4 w-4" />
                            Configurar
                          </Link>
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem className="text-red-600">
                          <Trash2 className="mr-2 h-4 w-4" />
                          Eliminar
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Quick Actions */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card className="cursor-pointer hover:shadow-md transition-shadow">
          <Link to="new?type=digital_signature">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <span className="text-2xl">📝</span>
                <span>Agente de Firma Digital</span>
              </CardTitle>
              <CardDescription>
                Crea un asistente para gestionar solicitudes de firma electrónica
              </CardDescription>
            </CardHeader>
          </Link>
        </Card>

        <Card className="cursor-pointer hover:shadow-md transition-shadow">
          <Link to="new?type=document_analyzer">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <span className="text-2xl">🔍</span>
                <span>Analizador de Documentos</span>
              </CardTitle>
              <CardDescription>
                Crea un asistente para análisis inteligente de documentos
              </CardDescription>
            </CardHeader>
          </Link>
        </Card>

        <Card className="cursor-pointer hover:shadow-md transition-shadow">
          <Link to="new?type=custom">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <span className="text-2xl">⚙️</span>
                <span>Agente Personalizado</span>
              </CardTitle>
              <CardDescription>
                Crea un agente personalizado con herramientas específicas
              </CardDescription>
            </CardHeader>
          </Link>
        </Card>
      </div>
    </div>
  );
}