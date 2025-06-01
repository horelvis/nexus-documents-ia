import { json, redirect, type ActionFunctionArgs, type LoaderFunctionArgs } from '@remix-run/node';
import { useLoaderData, Form, useNavigation, useSearchParams, Link } from '@remix-run/react';
import { useState } from 'react';
import { ArrowLeft, Upload, Plus, Trash2, Save, AlertCircle } from 'lucide-react';
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

interface SignatureProvider {
  id: string;
  provider_name: string;
  display_name: string;
  is_active: boolean;
  is_default: boolean;
}

interface DocumentTemplate {
  id: string;
  name: string;
  description: string;
  file_path: string;
}

interface Signer {
  id: string;
  name: string;
  email: string;
  phone?: string;
  order: number;
  authentication_method: string;
}

export async function loader({ request }: LoaderFunctionArgs) {
  // TODO: Fetch providers and templates from API
  const providers: SignatureProvider[] = [
    {
      id: '1',
      provider_name: 'docusign',
      display_name: 'DocuSign',
      is_active: true,
      is_default: true
    }
  ];

  const templates: DocumentTemplate[] = [
    {
      id: '1',
      name: 'Contrato de Servicios',
      description: 'Plantilla estándar para contratos de servicios profesionales',
      file_path: '/templates/contrato_servicios.pdf'
    },
    {
      id: '2',
      name: 'Acuerdo de Confidencialidad (NDA)',
      description: 'Acuerdo de no divulgación estándar',
      file_path: '/templates/nda_template.pdf'
    },
    {
      id: '3',
      name: 'Propuesta Comercial',
      description: 'Plantilla para propuestas y cotizaciones',
      file_path: '/templates/propuesta_comercial.pdf'
    }
  ];

  return json({ providers, templates });
}

export async function action({ request }: ActionFunctionArgs) {
  const formData = await request.formData();
  
  const signatureData = {
    title: formData.get('title'),
    message: formData.get('message'),
    provider_id: formData.get('provider_id'),
    signature_type: formData.get('signature_type'),
    document_file: formData.get('document_file'),
    template_id: formData.get('template_id'),
    expires_at: formData.get('expires_at'),
    signers: JSON.parse(formData.get('signers') as string || '[]')
  };

  // TODO: Call API to create signature request
  console.log('Creating signature request:', signatureData);

  return redirect('/dashboard/signatures');
}

export default function NewSignatureRequest() {
  const { providers, templates } = useLoaderData<typeof loader>();
  const navigation = useNavigation();
  const [searchParams] = useSearchParams();
  const templateParam = searchParams.get('template');

  const [selectedTemplate, setSelectedTemplate] = useState(templateParam || '');
  const [signers, setSigners] = useState<Signer[]>([
    {
      id: '1',
      name: '',
      email: '',
      phone: '',
      order: 1,
      authentication_method: 'email'
    }
  ]);
  const [signatureType, setSignatureType] = useState('sequential');
  const [useTemplate, setUseTemplate] = useState(!!templateParam);

  const addSigner = () => {
    const newSigner: Signer = {
      id: Date.now().toString(),
      name: '',
      email: '',
      phone: '',
      order: signers.length + 1,
      authentication_method: 'email'
    };
    setSigners([...signers, newSigner]);
  };

  const removeSigner = (id: string) => {
    if (signers.length > 1) {
      setSigners(signers.filter(s => s.id !== id));
    }
  };

  const updateSigner = (id: string, field: keyof Signer, value: string | number) => {
    setSigners(signers.map(s => 
      s.id === id ? { ...s, [field]: value } : s
    ));
  };

  const isSubmitting = navigation.state === 'submitting';
  const activeProvider = providers.find(p => p.is_active);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center space-x-4">
        <Link to="/dashboard/signatures">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Volver
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Nueva Solicitud de Firma</h1>
          <p className="text-muted-foreground">
            Crea una nueva solicitud de firma digital
          </p>
        </div>
      </div>

      {!activeProvider && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            No hay proveedores de firma configurados. 
            <Link to="/dashboard/signatures/providers" className="font-medium underline ml-1">
              Configurar proveedores
            </Link>
          </AlertDescription>
        </Alert>
      )}

      <Form method="post" className="space-y-6" encType="multipart/form-data">
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Basic Information */}
          <Card>
            <CardHeader>
              <CardTitle>Información del Documento</CardTitle>
              <CardDescription>
                Configuración básica de la solicitud
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="title">Título de la Solicitud</Label>
                <Input
                  id="title"
                  name="title"
                  placeholder="Ej: Contrato de Servicios - Cliente ABC"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="message">Mensaje para los Firmantes</Label>
                <Textarea
                  id="message"
                  name="message"
                  placeholder="Mensaje que recibirán los firmantes junto con el documento"
                  rows={3}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="provider_id">Proveedor de Firma</Label>
                <Select name="provider_id" defaultValue={activeProvider?.id} required>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecciona un proveedor" />
                  </SelectTrigger>
                  <SelectContent>
                    {providers.filter(p => p.is_active).map((provider) => (
                      <SelectItem key={provider.id} value={provider.id}>
                        <div className="flex items-center space-x-2">
                          <span>{provider.display_name}</span>
                          {provider.is_default && (
                            <Badge variant="outline" className="text-xs">
                              Por defecto
                            </Badge>
                          )}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="signature_type">Tipo de Firma</Label>
                <Select 
                  name="signature_type" 
                  value={signatureType} 
                  onValueChange={setSignatureType}
                  required
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="sequential">
                      <div>
                        <div className="font-medium">Secuencial</div>
                        <div className="text-xs text-muted-foreground">
                          Los firmantes firman uno después del otro
                        </div>
                      </div>
                    </SelectItem>
                    <SelectItem value="parallel">
                      <div>
                        <div className="font-medium">Paralelo</div>
                        <div className="text-xs text-muted-foreground">
                          Todos los firmantes pueden firmar al mismo tiempo
                        </div>
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="expires_at">Fecha de Vencimiento (Opcional)</Label>
                <Input
                  id="expires_at"
                  name="expires_at"
                  type="datetime-local"
                />
              </div>
            </CardContent>
          </Card>

          {/* Document Selection */}
          <Card>
            <CardHeader>
              <CardTitle>Documento</CardTitle>
              <CardDescription>
                Selecciona o sube el documento a firmar
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center space-x-2">
                <Checkbox 
                  id="use_template" 
                  checked={useTemplate}
                  onCheckedChange={setUseTemplate}
                />
                <Label htmlFor="use_template" className="text-sm">
                  Usar plantilla predefinida
                </Label>
              </div>

              {useTemplate ? (
                <div className="space-y-2">
                  <Label htmlFor="template_id">Plantilla</Label>
                  <Select 
                    name="template_id" 
                    value={selectedTemplate} 
                    onValueChange={setSelectedTemplate}
                    required={useTemplate}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Selecciona una plantilla" />
                    </SelectTrigger>
                    <SelectContent>
                      {templates.map((template) => (
                        <SelectItem key={template.id} value={template.id}>
                          <div>
                            <div className="font-medium">{template.name}</div>
                            <div className="text-xs text-muted-foreground">
                              {template.description}
                            </div>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : (
                <div className="space-y-2">
                  <Label htmlFor="document_file">Subir Documento</Label>
                  <div className="border-2 border-dashed border-muted-foreground/25 rounded-lg p-6">
                    <div className="text-center">
                      <Upload className="mx-auto h-12 w-12 text-muted-foreground" />
                      <div className="mt-4">
                        <Label htmlFor="document_file" className="cursor-pointer">
                          <span className="mt-2 block text-sm font-medium">
                            Haz clic para subir o arrastra aquí
                          </span>
                          <span className="mt-1 block text-xs text-muted-foreground">
                            PDF, DOC, DOCX hasta 10MB
                          </span>
                        </Label>
                        <Input
                          id="document_file"
                          name="document_file"
                          type="file"
                          accept=".pdf,.doc,.docx"
                          className="hidden"
                          required={!useTemplate}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Signers */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Firmantes</CardTitle>
                <CardDescription>
                  Configura las personas que deben firmar el documento
                </CardDescription>
              </div>
              <Button type="button" variant="outline" onClick={addSigner}>
                <Plus className="mr-2 h-4 w-4" />
                Agregar Firmante
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {signers.map((signer, index) => (
                <Card key={signer.id} className="p-4">
                  <div className="flex items-start justify-between mb-4">
                    <h4 className="font-medium">
                      Firmante {index + 1}
                      {signatureType === 'sequential' && (
                        <Badge variant="outline" className="ml-2">
                          Orden: {signer.order}
                        </Badge>
                      )}
                    </h4>
                    {signers.length > 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => removeSigner(signer.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                  
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor={`signer_name_${signer.id}`}>Nombre Completo</Label>
                      <Input
                        id={`signer_name_${signer.id}`}
                        value={signer.name}
                        onChange={(e) => updateSigner(signer.id, 'name', e.target.value)}
                        placeholder="Nombre del firmante"
                        required
                      />
                    </div>
                    
                    <div className="space-y-2">
                      <Label htmlFor={`signer_email_${signer.id}`}>Correo Electrónico</Label>
                      <Input
                        id={`signer_email_${signer.id}`}
                        type="email"
                        value={signer.email}
                        onChange={(e) => updateSigner(signer.id, 'email', e.target.value)}
                        placeholder="correo@ejemplo.com"
                        required
                      />
                    </div>
                    
                    <div className="space-y-2">
                      <Label htmlFor={`signer_phone_${signer.id}`}>Teléfono (Opcional)</Label>
                      <Input
                        id={`signer_phone_${signer.id}`}
                        value={signer.phone}
                        onChange={(e) => updateSigner(signer.id, 'phone', e.target.value)}
                        placeholder="+52 55 1234 5678"
                      />
                    </div>
                    
                    <div className="space-y-2">
                      <Label htmlFor={`signer_auth_${signer.id}`}>Método de Autenticación</Label>
                      <Select 
                        value={signer.authentication_method}
                        onValueChange={(value) => updateSigner(signer.id, 'authentication_method', value)}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="email">Email</SelectItem>
                          <SelectItem value="sms">SMS</SelectItem>
                          <SelectItem value="email_sms">Email + SMS</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Hidden input for signers data */}
        <input type="hidden" name="signers" value={JSON.stringify(signers)} />

        {/* Actions */}
        <div className="flex items-center justify-end space-x-4">
          <Link to="/dashboard/signatures">
            <Button variant="outline" type="button">
              Cancelar
            </Button>
          </Link>
          <Button type="submit" disabled={isSubmitting || !activeProvider}>
            {isSubmitting ? (
              <>
                <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-background border-t-foreground" />
                Creando...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Crear Solicitud
              </>
            )}
          </Button>
        </div>
      </Form>
    </div>
  );
}