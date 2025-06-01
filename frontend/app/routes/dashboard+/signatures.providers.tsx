import { json, type ActionFunctionArgs, type LoaderFunctionArgs } from '@remix-run/node';
import { useLoaderData, Form, useNavigation, Link, useFetcher } from '@remix-run/react';
import { useState } from 'react';
import { ArrowLeft, Plus, Settings, Shield, CheckCircle, XCircle, Edit, Trash2 } from 'lucide-react';
import { Button } from '~/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '~/components/ui/card';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { Textarea } from '~/components/ui/textarea';
import { Switch } from '~/components/ui/switch';
import { Badge } from '~/components/ui/badge';
import { Alert, AlertDescription } from '~/components/ui/alert';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '~/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '~/components/ui/select';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '~/components/ui/table';

interface SignatureProvider {
  id: string;
  provider_name: string;
  display_name: string;
  is_active: boolean;
  is_default: boolean;
  configuration: any;
  created_at: string;
  updated_at: string;
}

interface ProviderConfig {
  provider_name: string;
  display_name: string;
  api_key?: string;
  api_secret?: string;
  client_id?: string;
  client_secret?: string;
  environment: 'sandbox' | 'production';
  webhook_url?: string;
  is_active: boolean;
  is_default: boolean;
}

const AVAILABLE_PROVIDERS = [
  {
    name: 'docusign',
    display_name: 'DocuSign',
    description: 'Líder mundial en firma electrónica y gestión de acuerdos',
    fields: [
      { name: 'client_id', label: 'Integration Key', type: 'text', required: true },
      { name: 'client_secret', label: 'Secret Key', type: 'password', required: true },
      { name: 'user_id', label: 'User ID (GUID)', type: 'text', required: true },
      { name: 'account_id', label: 'Account ID', type: 'text', required: true }
    ]
  },
  {
    name: 'yousign',
    display_name: 'YouSign',
    description: 'Solución europea de firma electrónica conforme a eIDAS',
    fields: [
      { name: 'api_key', label: 'API Key', type: 'password', required: true },
      { name: 'organization_id', label: 'Organization ID', type: 'text', required: true }
    ]
  },
  {
    name: 'signaturit',
    display_name: 'Signaturit',
    description: 'Plataforma de firma electrónica con sede en España',
    fields: [
      { name: 'access_token', label: 'Access Token', type: 'password', required: true },
      { name: 'client_id', label: 'Client ID', type: 'text', required: false }
    ]
  }
];

export async function loader({ request }: LoaderFunctionArgs) {
  // TODO: Fetch providers from API
  const mockProviders: SignatureProvider[] = [
    {
      id: '1',
      provider_name: 'docusign',
      display_name: 'DocuSign',
      is_active: true,
      is_default: true,
      configuration: {
        environment: 'sandbox',
        webhook_url: 'https://api.empresa.com/webhooks/docusign'
      },
      created_at: '2024-01-06T10:00:00Z',
      updated_at: '2024-01-06T10:00:00Z'
    }
  ];

  return json({ providers: mockProviders, availableProviders: AVAILABLE_PROVIDERS });
}

export async function action({ request }: ActionFunctionArgs) {
  const formData = await request.formData();
  const action = formData.get('_action');
  
  if (action === 'create' || action === 'update') {
    const providerData = {
      provider_name: formData.get('provider_name'),
      display_name: formData.get('display_name'),
      environment: formData.get('environment'),
      webhook_url: formData.get('webhook_url'),
      is_active: formData.get('is_active') === 'on',
      is_default: formData.get('is_default') === 'on',
      credentials: {}
    };

    // Extract credentials based on provider type
    const provider = AVAILABLE_PROVIDERS.find(p => p.name === providerData.provider_name);
    if (provider) {
      provider.fields.forEach(field => {
        const value = formData.get(field.name);
        if (value) {
          providerData.credentials[field.name] = value;
        }
      });
    }

    console.log('Provider data:', providerData);
    // TODO: Call API to create/update provider
  } else if (action === 'delete') {
    const providerId = formData.get('provider_id');
    console.log('Deleting provider:', providerId);
    // TODO: Call API to delete provider
  } else if (action === 'test') {
    const providerId = formData.get('provider_id');
    console.log('Testing provider:', providerId);
    // TODO: Call API to test provider connection
  }

  return json({ success: true });
}

export default function SignatureProviders() {
  const { providers, availableProviders } = useLoaderData<typeof loader>();
  const navigation = useNavigation();
  const fetcher = useFetcher();
  
  const [selectedProvider, setSelectedProvider] = useState('');
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<SignatureProvider | null>(null);

  const isSubmitting = navigation.state === 'submitting';
  const selectedProviderConfig = availableProviders.find(p => p.name === selectedProvider);

  const handleEdit = (provider: SignatureProvider) => {
    setEditingProvider(provider);
    setSelectedProvider(provider.provider_name);
    setIsDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setIsDialogOpen(false);
    setEditingProvider(null);
    setSelectedProvider('');
  };

  const testConnection = (providerId: string) => {
    fetcher.submit(
      { _action: 'test', provider_id: providerId },
      { method: 'post' }
    );
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
            <h1 className="text-3xl font-bold tracking-tight">Proveedores de Firma</h1>
            <p className="text-muted-foreground">
              Configura los proveedores de firma electrónica
            </p>
          </div>
        </div>
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Agregar Proveedor
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>
                {editingProvider ? 'Editar Proveedor' : 'Nuevo Proveedor de Firma'}
              </DialogTitle>
              <DialogDescription>
                Configura un proveedor de firma electrónica para tu organización
              </DialogDescription>
            </DialogHeader>
            
            <Form method="post" className="space-y-4">
              <input type="hidden" name="_action" value={editingProvider ? 'update' : 'create'} />
              {editingProvider && <input type="hidden" name="provider_id" value={editingProvider.id} />}
              
              <div className="space-y-2">
                <Label htmlFor="provider_name">Proveedor</Label>
                <Select 
                  name="provider_name" 
                  value={selectedProvider} 
                  onValueChange={setSelectedProvider}
                  required
                  disabled={!!editingProvider}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecciona un proveedor" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableProviders.map((provider) => (
                      <SelectItem key={provider.name} value={provider.name}>
                        <div>
                          <div className="font-medium">{provider.display_name}</div>
                          <div className="text-xs text-muted-foreground">
                            {provider.description}
                          </div>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="display_name">Nombre para Mostrar</Label>
                <Input
                  id="display_name"
                  name="display_name"
                  defaultValue={editingProvider?.display_name || selectedProviderConfig?.display_name}
                  placeholder="Nombre personalizado del proveedor"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="environment">Entorno</Label>
                <Select name="environment" defaultValue={editingProvider?.configuration?.environment || 'sandbox'} required>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="sandbox">
                      <div>
                        <div className="font-medium">Sandbox (Pruebas)</div>
                        <div className="text-xs text-muted-foreground">
                          Para desarrollo y pruebas
                        </div>
                      </div>
                    </SelectItem>
                    <SelectItem value="production">
                      <div>
                        <div className="font-medium">Producción</div>
                        <div className="text-xs text-muted-foreground">
                          Para uso en vivo
                        </div>
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {selectedProviderConfig && (
                <div className="space-y-4">
                  <Label className="text-base font-medium">Credenciales de API</Label>
                  {selectedProviderConfig.fields.map((field) => (
                    <div key={field.name} className="space-y-2">
                      <Label htmlFor={field.name}>
                        {field.label}
                        {field.required && <span className="text-red-500 ml-1">*</span>}
                      </Label>
                      <Input
                        id={field.name}
                        name={field.name}
                        type={field.type}
                        placeholder={`Ingresa tu ${field.label}`}
                        required={field.required}
                      />
                    </div>
                  ))}
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="webhook_url">URL de Webhook (Opcional)</Label>
                <Input
                  id="webhook_url"
                  name="webhook_url"
                  type="url"
                  defaultValue={editingProvider?.configuration?.webhook_url}
                  placeholder="https://tu-app.com/webhooks/firma"
                />
                <p className="text-xs text-muted-foreground">
                  URL donde se enviarán las notificaciones de eventos
                </p>
              </div>

              <div className="flex items-center space-x-2">
                <Switch id="is_active" name="is_active" defaultChecked={editingProvider?.is_active ?? true} />
                <Label htmlFor="is_active">Activar proveedor</Label>
              </div>

              <div className="flex items-center space-x-2">
                <Switch id="is_default" name="is_default" defaultChecked={editingProvider?.is_default ?? false} />
                <Label htmlFor="is_default">Usar como proveedor por defecto</Label>
              </div>

              <DialogFooter>
                <Button type="button" variant="outline" onClick={handleCloseDialog}>
                  Cancelar
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? (
                    <>
                      <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-background border-t-foreground" />
                      {editingProvider ? 'Actualizando...' : 'Creando...'}
                    </>
                  ) : (
                    <>
                      <Settings className="mr-2 h-4 w-4" />
                      {editingProvider ? 'Actualizar' : 'Crear Proveedor'}
                    </>
                  )}
                </Button>
              </DialogFooter>
            </Form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Info Alert */}
      <Alert>
        <Shield className="h-4 w-4" />
        <AlertDescription>
          Las credenciales se almacenan de forma encriptada y segura. Solo los administradores pueden ver y editar esta configuración.
        </AlertDescription>
      </Alert>

      {/* Providers Table */}
      <Card>
        <CardHeader>
          <CardTitle>Proveedores Configurados</CardTitle>
          <CardDescription>
            Lista de proveedores de firma electrónica configurados
          </CardDescription>
        </CardHeader>
        <CardContent>
          {providers.length === 0 ? (
            <div className="text-center py-8">
              <Settings className="mx-auto h-12 w-12 text-muted-foreground" />
              <h3 className="mt-4 text-lg font-medium">No hay proveedores configurados</h3>
              <p className="mt-2 text-muted-foreground">
                Configura al menos un proveedor para comenzar a usar la firma digital
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Proveedor</TableHead>
                  <TableHead>Entorno</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Por Defecto</TableHead>
                  <TableHead>Última Actualización</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {providers.map((provider) => (
                  <TableRow key={provider.id}>
                    <TableCell>
                      <div>
                        <div className="font-medium">{provider.display_name}</div>
                        <div className="text-sm text-muted-foreground">
                          {provider.provider_name}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={provider.configuration?.environment === 'production' ? 'default' : 'secondary'}>
                        {provider.configuration?.environment === 'production' ? 'Producción' : 'Sandbox'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center space-x-2">
                        {provider.is_active ? (
                          <CheckCircle className="h-4 w-4 text-green-500" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-500" />
                        )}
                        <span>{provider.is_active ? 'Activo' : 'Inactivo'}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {provider.is_default && (
                        <Badge variant="outline">Por defecto</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      <time dateTime={provider.updated_at}>
                        {new Date(provider.updated_at).toLocaleDateString('es-ES')}
                      </time>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end space-x-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => testConnection(provider.id)}
                          disabled={fetcher.state === 'submitting'}
                        >
                          {fetcher.state === 'submitting' ? (
                            <div className="h-4 w-4 animate-spin rounded-full border-2 border-background border-t-foreground" />
                          ) : (
                            'Probar'
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleEdit(provider)}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Form method="post" className="inline">
                          <input type="hidden" name="_action" value="delete" />
                          <input type="hidden" name="provider_id" value={provider.id} />
                          <Button
                            variant="ghost"
                            size="sm"
                            type="submit"
                            className="text-red-600 hover:text-red-700"
                            onClick={(e) => {
                              if (!confirm('¿Estás seguro de que quieres eliminar este proveedor?')) {
                                e.preventDefault();
                              }
                            }}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </Form>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Quick Setup Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {availableProviders.map((provider) => (
          <Card key={provider.name} className="cursor-pointer hover:shadow-md transition-shadow">
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>{provider.display_name}</span>
                {providers.some(p => p.provider_name === provider.name) && (
                  <Badge variant="secondary">Configurado</Badge>
                )}
              </CardTitle>
              <CardDescription>
                {provider.description}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button 
                variant="outline" 
                className="w-full"
                onClick={() => {
                  setSelectedProvider(provider.name);
                  setIsDialogOpen(true);
                }}
                disabled={providers.some(p => p.provider_name === provider.name)}
              >
                {providers.some(p => p.provider_name === provider.name) ? 'Ya Configurado' : 'Configurar'}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}