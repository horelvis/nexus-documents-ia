import { json, type LoaderFunctionArgs } from '@remix-run/node';
import { useLoaderData, Link, Form, useNavigation } from '@remix-run/react';
import { Plus, FileSignature, Clock, CheckCircle, XCircle, AlertCircle, Download, Eye, Send } from 'lucide-react';
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
import { Progress } from '~/components/ui/progress';

interface SignatureRequest {
  id: string;
  title: string;
  document_name: string;
  status: string;
  created_at: string;
  sent_at: string | null;
  completed_at: string | null;
  expires_at: string | null;
  signers: SignatureRequestSigner[];
}

interface SignatureRequestSigner {
  id: string;
  name: string;
  email: string;
  status: string;
  order: number;
  signed_at: string | null;
}

interface SignatureProvider {
  id: string;
  provider_name: string;
  display_name: string;
  is_active: boolean;
  is_default: boolean;
}

export async function loader({ request }: LoaderFunctionArgs) {
  // TODO: Fetch signature requests and providers from API
  const mockRequests: SignatureRequest[] = [
    {
      id: '1',
      title: 'Contrato de Servicios - Cliente ABC',
      document_name: 'contrato_servicios_abc.pdf',
      status: 'in_progress',
      created_at: '2024-01-06T10:00:00Z',
      sent_at: '2024-01-06T10:30:00Z',
      completed_at: null,
      expires_at: '2024-01-13T10:30:00Z',
      signers: [
        {
          id: '1',
          name: 'Juan Pérez',
          email: 'juan.perez@abc.com',
          status: 'signed',
          order: 1,
          signed_at: '2024-01-06T14:20:00Z'
        },
        {
          id: '2',
          name: 'María García',
          email: 'maria.garcia@empresa.com',
          status: 'sent',
          order: 2,
          signed_at: null
        }
      ]
    },
    {
      id: '2',
      title: 'Acuerdo de Confidencialidad',
      document_name: 'nda_template.pdf',
      status: 'completed',
      created_at: '2024-01-05T09:00:00Z',
      sent_at: '2024-01-05T09:15:00Z',
      completed_at: '2024-01-05T16:45:00Z',
      expires_at: null,
      signers: [
        {
          id: '3',
          name: 'Carlos López',
          email: 'carlos.lopez@cliente.com',
          status: 'signed',
          order: 1,
          signed_at: '2024-01-05T16:45:00Z'
        }
      ]
    },
    {
      id: '3',
      title: 'Propuesta Comercial Q1 2024',
      document_name: 'propuesta_q1_2024.pdf',
      status: 'draft',
      created_at: '2024-01-06T15:00:00Z',
      sent_at: null,
      completed_at: null,
      expires_at: null,
      signers: [
        {
          id: '4',
          name: 'Ana Martínez',
          email: 'ana.martinez@prospect.com',
          status: 'pending',
          order: 1,
          signed_at: null
        },
        {
          id: '5',
          name: 'Luis Rodriguez',
          email: 'luis.rodriguez@prospect.com',
          status: 'pending',
          order: 2,
          signed_at: null
        }
      ]
    }
  ];

  const mockProviders: SignatureProvider[] = [
    {
      id: '1',
      provider_name: 'docusign',
      display_name: 'DocuSign',
      is_active: true,
      is_default: true
    }
  ];

  return json({ 
    requests: mockRequests,
    providers: mockProviders
  });
}

export default function SignaturesIndex() {
  const { requests, providers } = useLoaderData<typeof loader>();
  const navigation = useNavigation();

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'in_progress':
        return 'bg-blue-100 text-blue-800';
      case 'sent':
        return 'bg-yellow-100 text-yellow-800';
      case 'draft':
        return 'bg-gray-100 text-gray-800';
      case 'declined':
        return 'bg-red-100 text-red-800';
      case 'expired':
        return 'bg-orange-100 text-orange-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4" />;
      case 'in_progress':
        return <Clock className="h-4 w-4" />;
      case 'sent':
        return <Send className="h-4 w-4" />;
      case 'draft':
        return <FileSignature className="h-4 w-4" />;
      case 'declined':
        return <XCircle className="h-4 w-4" />;
      case 'expired':
        return <AlertCircle className="h-4 w-4" />;
      default:
        return <FileSignature className="h-4 w-4" />;
    }
  };

  const getStatusText = (status: string) => {
    const statusMap: { [key: string]: string } = {
      'draft': 'Borrador',
      'sent': 'Enviada',
      'in_progress': 'En Progreso',
      'completed': 'Completada',
      'declined': 'Rechazada',
      'expired': 'Expirada'
    };
    return statusMap[status] || status;
  };

  const calculateProgress = (signers: SignatureRequestSigner[]) => {
    const signedCount = signers.filter(s => s.status === 'signed').length;
    return (signedCount / signers.length) * 100;
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('es-ES', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const isExpiringSoon = (expiresAt: string | null) => {
    if (!expiresAt) return false;
    const expireDate = new Date(expiresAt);
    const now = new Date();
    const diffHours = (expireDate.getTime() - now.getTime()) / (1000 * 60 * 60);
    return diffHours > 0 && diffHours <= 24;
  };

  // Statistics
  const totalRequests = requests.length;
  const completedRequests = requests.filter(r => r.status === 'completed').length;
  const pendingRequests = requests.filter(r => ['sent', 'in_progress'].includes(r.status)).length;
  const completionRate = totalRequests > 0 ? (completedRequests / totalRequests * 100).toFixed(1) : '0';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Firma Digital</h1>
          <p className="text-muted-foreground">
            Gestiona solicitudes de firma electrónica y documentos
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Link to="providers">
            <Button variant="outline">
              Configurar Proveedores
            </Button>
          </Link>
          <Link to="new">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Nueva Solicitud
            </Button>
          </Link>
        </div>
      </div>

      {/* Statistics Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Solicitudes</CardTitle>
            <FileSignature className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalRequests}</div>
            <p className="text-xs text-muted-foreground">
              Este mes
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Completadas</CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{completedRequests}</div>
            <p className="text-xs text-muted-foreground">
              Tasa: {completionRate}%
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pendientes</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{pendingRequests}</div>
            <p className="text-xs text-muted-foreground">
              Esperando firmas
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Proveedores</CardTitle>
            <Eye className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{providers.length}</div>
            <p className="text-xs text-muted-foreground">
              {providers.filter(p => p.is_active).length} activos
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Requests Table */}
      <Card>
        <CardHeader>
          <CardTitle>Solicitudes de Firma</CardTitle>
          <CardDescription>
            Gestiona todas tus solicitudes de firma digital
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Documento</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Progreso</TableHead>
                <TableHead>Firmantes</TableHead>
                <TableHead>Creada</TableHead>
                <TableHead>Vencimiento</TableHead>
                <TableHead className="text-right">Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {requests.map((request) => (
                <TableRow key={request.id}>
                  <TableCell>
                    <div>
                      <div className="font-medium">{request.title}</div>
                      <div className="text-sm text-muted-foreground">
                        {request.document_name}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge className={getStatusColor(request.status)}>
                      <div className="flex items-center space-x-1">
                        {getStatusIcon(request.status)}
                        <span>{getStatusText(request.status)}</span>
                      </div>
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="space-y-1">
                      <Progress value={calculateProgress(request.signers)} className="h-2" />
                      <div className="text-xs text-muted-foreground">
                        {request.signers.filter(s => s.status === 'signed').length} de {request.signers.length} firmado(s)
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="space-y-1">
                      {request.signers.slice(0, 2).map((signer) => (
                        <div key={signer.id} className="flex items-center space-x-2">
                          <div className={`w-2 h-2 rounded-full ${
                            signer.status === 'signed' ? 'bg-green-500' : 
                            signer.status === 'sent' ? 'bg-yellow-500' : 'bg-gray-300'
                          }`} />
                          <span className="text-sm">{signer.name}</span>
                        </div>
                      ))}
                      {request.signers.length > 2 && (
                        <div className="text-xs text-muted-foreground">
                          +{request.signers.length - 2} más
                        </div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <time dateTime={request.created_at}>
                      {formatDate(request.created_at)}
                    </time>
                  </TableCell>
                  <TableCell>
                    {request.expires_at ? (
                      <div className={`text-sm ${
                        isExpiringSoon(request.expires_at) ? 'text-orange-600 font-medium' : ''
                      }`}>
                        {formatDate(request.expires_at)}
                        {isExpiringSoon(request.expires_at) && (
                          <div className="text-xs text-orange-600">
                            ⚠️ Expira pronto
                          </div>
                        )}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" className="h-8 w-8 p-0">
                          <span className="sr-only">Abrir menú</span>
                          <Eye className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuLabel>Acciones</DropdownMenuLabel>
                        <DropdownMenuItem asChild>
                          <Link to={`${request.id}`}>
                            <Eye className="mr-2 h-4 w-4" />
                            Ver Detalles
                          </Link>
                        </DropdownMenuItem>
                        {request.status === 'draft' && (
                          <DropdownMenuItem>
                            <Send className="mr-2 h-4 w-4" />
                            Enviar
                          </DropdownMenuItem>
                        )}
                        {request.status === 'completed' && (
                          <DropdownMenuItem>
                            <Download className="mr-2 h-4 w-4" />
                            Descargar
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem asChild>
                          <Link to={`${request.id}/edit`}>
                            Editar
                          </Link>
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
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="cursor-pointer hover:shadow-md transition-shadow">
          <Link to="new?template=contract">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <span className="text-2xl">📄</span>
                <span>Contrato de Servicios</span>
              </CardTitle>
              <CardDescription>
                Plantilla para contratos de servicios profesionales
              </CardDescription>
            </CardHeader>
          </Link>
        </Card>

        <Card className="cursor-pointer hover:shadow-md transition-shadow">
          <Link to="new?template=nda">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <span className="text-2xl">🔒</span>
                <span>Acuerdo de Confidencialidad</span>
              </CardTitle>
              <CardDescription>
                Plantilla para acuerdos de no divulgación (NDA)
              </CardDescription>
            </CardHeader>
          </Link>
        </Card>

        <Card className="cursor-pointer hover:shadow-md transition-shadow">
          <Link to="new?template=proposal">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <span className="text-2xl">💼</span>
                <span>Propuesta Comercial</span>
              </CardTitle>
              <CardDescription>
                Plantilla para propuestas y cotizaciones
              </CardDescription>
            </CardHeader>
          </Link>
        </Card>
      </div>
    </div>
  );
}