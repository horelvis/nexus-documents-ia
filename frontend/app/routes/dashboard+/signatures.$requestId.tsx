import { json, type LoaderFunctionArgs } from '@remix-run/node';
import { useLoaderData, Link, Form, useNavigation } from '@remix-run/react';
import { ArrowLeft, Download, Send, RefreshCw, CheckCircle, Clock, XCircle, AlertCircle, Eye, User, Calendar, Mail, Phone, MapPin } from 'lucide-react';
import { Button } from '~/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '~/components/ui/card';
import { Badge } from '~/components/ui/badge';
import { Progress } from '~/components/ui/progress';
import { Separator } from '~/components/ui/separator';
import { Alert, AlertDescription } from '~/components/ui/alert';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';

interface SignatureRequest {
  id: string;
  title: string;
  document_name: string;
  status: string;
  created_at: string;
  sent_at: string | null;
  completed_at: string | null;
  expires_at: string | null;
  message: string | null;
  signature_type: string;
  provider: {
    id: string;
    display_name: string;
    provider_name: string;
  };
  signers: SignatureRequestSigner[];
  events: SignatureEvent[];
  metadata: any;
}

interface SignatureRequestSigner {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  order: number;
  status: string;
  signed_at: string | null;
  ip_address: string | null;
  user_agent: string | null;
  authentication_method: string;
  signing_url: string | null;
}

interface SignatureEvent {
  id: string;
  event_type: string;
  description: string;
  created_at: string;
  event_data: any;
}

export async function loader({ params }: LoaderFunctionArgs) {
  const requestId = params.requestId;
  
  // TODO: Fetch signature request from API
  const mockRequest: SignatureRequest = {
    id: requestId!,
    title: 'Contrato de Servicios - Cliente ABC',
    document_name: 'contrato_servicios_abc.pdf',
    status: 'in_progress',
    created_at: '2024-01-06T10:00:00Z',
    sent_at: '2024-01-06T10:30:00Z',
    completed_at: null,
    expires_at: '2024-01-13T10:30:00Z',
    message: 'Por favor, revise y firme este contrato de servicios. Si tiene alguna pregunta, no dude en contactarnos.',
    signature_type: 'sequential',
    provider: {
      id: '1',
      display_name: 'DocuSign',
      provider_name: 'docusign'
    },
    signers: [
      {
        id: '1',
        name: 'Juan Pérez',
        email: 'juan.perez@abc.com',
        phone: '+52 55 1234 5678',
        order: 1,
        status: 'signed',
        signed_at: '2024-01-06T14:20:00Z',
        ip_address: '192.168.1.100',
        user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        authentication_method: 'email',
        signing_url: null
      },
      {
        id: '2',
        name: 'María García',
        email: 'maria.garcia@empresa.com',
        phone: '+52 55 8765 4321',
        order: 2,
        status: 'sent',
        signed_at: null,
        ip_address: null,
        user_agent: null,
        authentication_method: 'email_sms',
        signing_url: 'https://app.docusign.com/signing/abc123'
      }
    ],
    events: [
      {
        id: '1',
        event_type: 'request_created',
        description: 'Solicitud de firma creada',
        created_at: '2024-01-06T10:00:00Z',
        event_data: {}
      },
      {
        id: '2',
        event_type: 'request_sent',
        description: 'Solicitud enviada a los firmantes',
        created_at: '2024-01-06T10:30:00Z',
        event_data: { recipients_count: 2 }
      },
      {
        id: '3',
        event_type: 'signer_signed',
        description: 'Juan Pérez firmó el documento',
        created_at: '2024-01-06T14:20:00Z',
        event_data: { signer_id: '1', signer_name: 'Juan Pérez' }
      }
    ],
    metadata: {
      document_size: '2.1 MB',
      pages: 5,
      external_reference: 'CONT-2024-001'
    }
  };

  return json({ request: mockRequest });
}

export default function SignatureRequestDetail() {
  const { request } = useLoaderData<typeof loader>();
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
      case 'signed':
        return 'bg-green-100 text-green-800';
      case 'pending':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
      case 'signed':
        return <CheckCircle className="h-4 w-4" />;
      case 'in_progress':
      case 'sent':
        return <Clock className="h-4 w-4" />;
      case 'draft':
      case 'pending':
        return <AlertCircle className="h-4 w-4" />;
      case 'declined':
      case 'expired':
        return <XCircle className="h-4 w-4" />;
      default:
        return <AlertCircle className="h-4 w-4" />;
    }
  };

  const getStatusText = (status: string) => {
    const statusMap: { [key: string]: string } = {
      'draft': 'Borrador',
      'sent': 'Enviada',
      'in_progress': 'En Progreso',
      'completed': 'Completada',
      'declined': 'Rechazada',
      'expired': 'Expirada',
      'signed': 'Firmado',
      'pending': 'Pendiente'
    };
    return statusMap[status] || status;
  };

  const calculateProgress = () => {
    const signedCount = request.signers.filter(s => s.status === 'signed').length;
    return (signedCount / request.signers.length) * 100;
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

  const getEventIcon = (eventType: string) => {
    switch (eventType) {
      case 'request_created':
        return '📄';
      case 'request_sent':
        return '📤';
      case 'signer_signed':
        return '✅';
      case 'signer_declined':
        return '❌';
      case 'request_completed':
        return '🎉';
      case 'request_expired':
        return '⏰';
      default:
        return '📝';
    }
  };

  const isExpiringSoon = () => {
    if (!request.expires_at) return false;
    const expireDate = new Date(request.expires_at);
    const now = new Date();
    const diffHours = (expireDate.getTime() - now.getTime()) / (1000 * 60 * 60);
    return diffHours > 0 && diffHours <= 24;
  };

  const canResendReminder = () => {
    return ['sent', 'in_progress'].includes(request.status);
  };

  const canDownload = () => {
    return request.status === 'completed';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link to="/dashboard/signatures">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Volver
            </Button>
          </Link>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">{request.title}</h1>
            <p className="text-muted-foreground">{request.document_name}</p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          {canDownload() && (
            <Button variant="outline">
              <Download className="mr-2 h-4 w-4" />
              Descargar
            </Button>
          )}
          {canResendReminder() && (
            <Form method="post">
              <input type="hidden" name="_action" value="resend_reminder" />
              <Button variant="outline" type="submit">
                <Send className="mr-2 h-4 w-4" />
                Recordatorio
              </Button>
            </Form>
          )}
          <Button variant="outline">
            <RefreshCw className="mr-2 h-4 w-4" />
            Actualizar
          </Button>
        </div>
      </div>

      {/* Status Alert */}
      {isExpiringSoon() && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Esta solicitud expira pronto: {formatDate(request.expires_at!)}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          {/* Request Overview */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <span>Estado de la Solicitud</span>
                <Badge className={getStatusColor(request.status)}>
                  <div className="flex items-center space-x-1">
                    {getStatusIcon(request.status)}
                    <span>{getStatusText(request.status)}</span>
                  </div>
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="flex justify-between text-sm mb-2">
                  <span>Progreso de Firmas</span>
                  <span>{request.signers.filter(s => s.status === 'signed').length} de {request.signers.length} firmado(s)</span>
                </div>
                <Progress value={calculateProgress()} className="h-2" />
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">Creada:</span>
                  <div>{formatDate(request.created_at)}</div>
                </div>
                <div>
                  <span className="text-muted-foreground">Enviada:</span>
                  <div>{request.sent_at ? formatDate(request.sent_at) : 'No enviada'}</div>
                </div>
                <div>
                  <span className="text-muted-foreground">Tipo de Firma:</span>
                  <div>{request.signature_type === 'sequential' ? 'Secuencial' : 'Paralelo'}</div>
                </div>
                <div>
                  <span className="text-muted-foreground">Proveedor:</span>
                  <div>{request.provider.display_name}</div>
                </div>
              </div>

              {request.message && (
                <div>
                  <span className="text-muted-foreground text-sm">Mensaje:</span>
                  <div className="mt-1 p-3 bg-muted rounded-md text-sm">
                    {request.message}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Signers */}
          <Card>
            <CardHeader>
              <CardTitle>Firmantes</CardTitle>
              <CardDescription>
                Estado y detalles de cada firmante
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {request.signers.map((signer, index) => (
                  <div key={signer.id} className="border rounded-lg p-4">
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center space-x-3">
                        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-100 text-blue-800 text-sm font-medium">
                          {index + 1}
                        </div>
                        <div>
                          <h4 className="font-medium">{signer.name}</h4>
                          <p className="text-sm text-muted-foreground">{signer.email}</p>
                        </div>
                      </div>
                      <Badge className={getStatusColor(signer.status)}>
                        <div className="flex items-center space-x-1">
                          {getStatusIcon(signer.status)}
                          <span>{getStatusText(signer.status)}</span>
                        </div>
                      </Badge>
                    </div>

                    <div className="grid grid-cols-2 gap-4 text-sm">
                      {signer.phone && (
                        <div className="flex items-center space-x-2">
                          <Phone className="h-4 w-4 text-muted-foreground" />
                          <span>{signer.phone}</span>
                        </div>
                      )}
                      <div className="flex items-center space-x-2">
                        <Mail className="h-4 w-4 text-muted-foreground" />
                        <span>{signer.authentication_method.replace('_', ' + ')}</span>
                      </div>
                      {signer.signed_at && (
                        <div className="flex items-center space-x-2">
                          <Calendar className="h-4 w-4 text-muted-foreground" />
                          <span>Firmado: {formatDate(signer.signed_at)}</span>
                        </div>
                      )}
                      {signer.ip_address && (
                        <div className="flex items-center space-x-2">
                          <MapPin className="h-4 w-4 text-muted-foreground" />
                          <span>IP: {signer.ip_address}</span>
                        </div>
                      )}
                    </div>

                    {signer.signing_url && signer.status !== 'signed' && (
                      <div className="mt-3 pt-3 border-t">
                        <a
                          href={signer.signing_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                        >
                          Ver enlace de firma →
                        </a>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          {/* Document Info */}
          <Card>
            <CardHeader>
              <CardTitle>Información del Documento</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center space-x-2">
                <Eye className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">{request.document_name}</span>
              </div>
              {request.metadata?.document_size && (
                <div className="text-sm text-muted-foreground">
                  Tamaño: {request.metadata.document_size}
                </div>
              )}
              {request.metadata?.pages && (
                <div className="text-sm text-muted-foreground">
                  Páginas: {request.metadata.pages}
                </div>
              )}
              {request.metadata?.external_reference && (
                <div className="text-sm text-muted-foreground">
                  Ref: {request.metadata.external_reference}
                </div>
              )}
              {request.expires_at && (
                <div className="text-sm">
                  <span className="text-muted-foreground">Expira: </span>
                  <span className={isExpiringSoon() ? 'text-orange-600 font-medium' : ''}>
                    {formatDate(request.expires_at)}
                  </span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Activity Timeline */}
          <Card>
            <CardHeader>
              <CardTitle>Historial de Actividad</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {request.events.map((event, index) => (
                  <div key={event.id} className="flex space-x-3">
                    <div className="flex items-center justify-center w-8 h-8 rounded-full bg-gray-100 text-sm">
                      {getEventIcon(event.event_type)}
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium">{event.description}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatDate(event.created_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}