'use client'

import React, { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import Image from 'next/image'
import { 
  Building, 
  User, 
  Upload, 
  ArrowRight, 
  ArrowLeft,
  Check,
  FileText,
  Cloud,
  PenTool,
  Sparkles,
  Bot,
  Search,
  Shield,
  Zap
} from 'lucide-react'
import { useUserContext } from '@/contexts/user-context'

// Zod schema for validation
const companyFormSchema = z.object({
  companyName: z.string().min(1, "El nombre de la empresa es requerido").min(2, "El nombre debe tener al menos 2 caracteres"),
  cif: z.string().min(1, "El CIF/NIF es requerido").regex(/^[A-Z]\d{8}$|^\d{8}[A-Z]$/, "Formato de CIF/NIF inválido"),
  address: z.string().optional(),
  phone: z.string().optional(),
  website: z.string().url("Debe ser una URL válida").optional().or(z.literal("")),
})

type CompanyFormData = z.infer<typeof companyFormSchema>

interface CompanyData extends CompanyFormData {
  logo?: File | null
}

interface OnboardingWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onComplete: () => void
}

export function OnboardingWizard({ open, onOpenChange, onComplete }: OnboardingWizardProps) {
  const { clerkUser, syncUserWithBackend, markOnboardingComplete } = useUserContext()
  const [currentStep, setCurrentStep] = useState(1) // Start at company data step
  
  // Form setup
  const form = useForm<CompanyFormData>({
    resolver: zodResolver(companyFormSchema),
    defaultValues: {
      companyName: '',
      cif: '',
      address: '',
      phone: '',
      website: ''
    }
  })
  
  const [logoData, setLogoData] = useState<{ file: File | null; preview: string | null }>({
    file: null,
    preview: null
  })
  
  const [googleDriveConnected, setGoogleDriveConnected] = useState(false)
  const [signatureProvider, setSignatureProvider] = useState<string>('')

  const steps = [
    {
      id: 'user-data',
      title: 'Datos de Usuario',
      description: 'Verificar información personal',
      icon: <User className="h-5 w-5" />
    },
    {
      id: 'company-data',
      title: 'Datos Empresariales',
      description: 'Información de tu empresa',
      icon: <Building className="h-5 w-5" />
    },
    {
      id: 'google-drive',
      title: 'Conectar Google Drive',
      description: 'Sincronizar documentos (opcional)',
      icon: <Cloud className="h-5 w-5" />
    },
    {
      id: 'signature-provider',
      title: 'Proveedor de Firma',
      description: 'Configurar firma digital',
      icon: <PenTool className="h-5 w-5" />
    },
    {
      id: 'features-overview',
      title: 'Funcionalidades',
      description: 'Descubre las características',
      icon: <Sparkles className="h-5 w-5" />
    }
  ]

  // Sync user when wizard opens (but don't block UI)
  useEffect(() => {
    const syncUser = async () => {
      if (open && clerkUser) {
        try {
          await syncUserWithBackend()
        } catch (error) {
          console.error('Error syncing user:', error)
        }
      }
    }
    
    syncUser()
  }, [open, clerkUser, syncUserWithBackend])

  const handleNext = async () => {
    // Validate current step before proceeding
    if (currentStep === 1) {
      const isValid = await form.trigger()
      if (!isValid) return
    }
    
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1)
    } else {
      handleComplete()
    }
  }

  const handlePrevious = () => {
    if (currentStep > 1) { // Don't go back to step 0
      setCurrentStep(currentStep - 1)
    }
  }

  const handleComplete = async () => {
    try {
      // En el último paso, redirigir a pricing en lugar de completar onboarding
      // El onboarding solo se completará después de un pago exitoso
      if (currentStep === steps.length - 1) {
        // Guardar datos del formulario en localStorage para uso posterior
        const formData = form.getValues()
        const onboardingData = {
          company_name: formData.companyName,
          cif: formData.cif,
          address: formData.address,
          phone: formData.phone,
          website: formData.website,
          google_drive_connected: googleDriveConnected,
          signature_provider: signatureProvider || null
        }
        
        localStorage.setItem('pendingOnboardingData', JSON.stringify(onboardingData))
        
        // Redirigir a pricing para forzar el pago
        window.location.href = '/pricing'
        return
      }
      
      // Para otros pasos, continuar normalmente
      await markOnboardingComplete()
      onComplete()
      onOpenChange(false)
    } catch (error) {
      console.error('Error completing onboarding:', error)
    }
  }

  const handleLogoUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      // Create preview URL
      const reader = new FileReader()
      reader.onload = (e) => {
        setLogoData({
          file: file,
          preview: e.target?.result as string
        })
      }
      reader.readAsDataURL(file)
    }
  }

  const connectGoogleDrive = () => {
    // TODO: Implement Google Drive OAuth
    setGoogleDriveConnected(true)
  }

  const progressPercentage = ((currentStep + 1) / steps.length) * 100

  const canProceed = () => {
    switch (currentStep) {
      case 0:
        return true
      case 1:
        return form.formState.isValid
      case 2:
        return true // Optional step
      case 3:
        return true // Optional step
      case 4:
        return true
      default:
        return true
    }
  }

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="max-w-[1600px] w-[98vw] max-h-[95vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-blue-600" />
            Bienvenido a Nexus - Configuración Inicial
          </DialogTitle>
        </DialogHeader>

        {/* Progress Bar */}
        <div className="mb-6">
          <div className="flex items-center justify-between text-sm text-gray-600 mb-2">
            <span>Paso {currentStep + 1} de {steps.length}</span>
            <span>{Math.round(progressPercentage)}% completado</span>
          </div>
          <Progress value={progressPercentage} className="w-full" />
        </div>

        {/* Steps Navigation */}
        <div className="flex justify-center mb-8">
          <div className="flex items-center space-x-4">
            {steps.map((step, index) => (
              <div key={step.id} className="flex items-center">
                <div
                  className={`flex items-center justify-center w-12 h-12 rounded-full transition-all duration-200 ${
                    index === currentStep
                      ? 'bg-blue-600 text-white shadow-lg scale-110'
                      : index < currentStep
                      ? 'bg-green-600 text-white'
                      : 'bg-gray-200 text-gray-400'
                  }`}
                >
                  {index < currentStep ? (
                    <Check className="h-5 w-5" />
                  ) : (
                    <div className="scale-100">
                      {React.cloneElement(step.icon as React.ReactElement<{ className?: string }>, { 
                        className: "h-5 w-5" 
                      })}
                    </div>
                  )}
                </div>
                {index < steps.length - 1 && (
                  <div className={`w-8 h-0.5 mx-2 ${
                    index < currentStep ? 'bg-green-600' : 'bg-gray-200'
                  }`} />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Current Step Title and Description */}
        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            {steps[currentStep]?.title}
          </h2>
          <p className="text-gray-600 text-lg">
            {steps[currentStep]?.description}
          </p>
        </div>

        {/* Step Content */}
        <div className="min-h-[400px]">
          {/* Step 0: User Data */}
          {currentStep === 0 && (
            <Card>
              <CardContent className="space-y-6 pt-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Nombre Completo</Label>
                    <Input
                      value={`${clerkUser?.firstName || ''} ${clerkUser?.lastName || ''}`.trim()}
                      disabled
                      className="bg-gray-50"
                    />
                  </div>
                  <div>
                    <Label>Email</Label>
                    <Input
                      value={clerkUser?.emailAddresses[0]?.emailAddress || ''}
                      disabled
                      className="bg-gray-50"
                    />
                  </div>
                </div>
                <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                  <p className="text-sm text-blue-800">
                    <strong>Nota:</strong> Estos datos provienen de tu autenticación. 
                    Si necesitas modificarlos, puedes hacerlo desde tu perfil después del registro.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Step 1: Company Data */}
          {currentStep === 1 && (
            <Card>
              <CardContent className="space-y-6 pt-6">
                <Form {...form}>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <FormField
                      control={form.control}
                      name="companyName"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Nombre de la Empresa *</FormLabel>
                          <FormControl>
                            <Input placeholder="Ej: Mi Empresa SL" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="cif"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>CIF/NIF *</FormLabel>
                          <FormControl>
                            <Input placeholder="Ej: B12345678" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                  
                  <FormField
                    control={form.control}
                    name="address"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Dirección</FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder="Dirección completa de la empresa"
                            rows={2}
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <FormField
                      control={form.control}
                      name="phone"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Teléfono</FormLabel>
                          <FormControl>
                            <Input placeholder="Ej: +34 123 456 789" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="website"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Sitio Web</FormLabel>
                          <FormControl>
                            <Input placeholder="Ej: https://miempresa.com" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </Form>

                <div>
                  <Label>Logo de la Empresa</Label>
                  <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center">
                    {logoData.preview ? (
                      <div className="space-y-4">
                        <div className="flex justify-center">
                          <Image 
                            src={logoData.preview} 
                            alt="Preview del logo" 
                            width={128}
                            height={128}
                            className="max-w-32 max-h-32 object-contain rounded-lg border"
                          />
                        </div>
                        <p className="text-xs text-green-600">
                          ✓ {logoData.file?.name}
                        </p>
                        <Button variant="outline" size="sm" asChild>
                          <label htmlFor="logo-upload" className="cursor-pointer">
                            Cambiar Imagen
                          </label>
                        </Button>
                      </div>
                    ) : (
                      <>
                        <Upload className="h-8 w-8 mx-auto text-gray-400 mb-2" />
                        <p className="text-sm text-gray-600 mb-2">
                          Arrastra y suelta tu logo aquí, o haz clic para seleccionar
                        </p>
                        <Button variant="outline" size="sm" asChild>
                          <label htmlFor="logo-upload" className="cursor-pointer">
                            Seleccionar Archivo
                          </label>
                        </Button>
                      </>
                    )}
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleLogoUpload}
                      className="hidden"
                      id="logo-upload"
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Step 2: Google Drive */}
          {currentStep === 2 && (
            <Card>
              <CardContent className="space-y-6 pt-6">
                <div className="text-center">
                  <div className="w-20 h-20 mx-auto mb-6 bg-blue-100 rounded-full flex items-center justify-center">
                    <Cloud className="h-10 w-10 text-blue-600" />
                  </div>
                  <p className="text-gray-600 mb-6 text-lg">
                    Conecta tu Google Drive para sincronizar automáticamente tus documentos 
                    y mantener todo organizado en un solo lugar.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 border rounded-lg">
                    <FileText className="h-6 w-6 text-green-600 mb-2" />
                    <h4 className="font-semibold">Acceso a Documentos</h4>
                    <p className="text-sm text-gray-600">
                      Accede a todos tus archivos desde Nexus
                    </p>
                  </div>
                  <div className="p-4 border rounded-lg">
                    <Zap className="h-6 w-6 text-yellow-600 mb-2" />
                    <h4 className="font-semibold">Sincronización Automática</h4>
                    <p className="text-sm text-gray-600">
                      Los cambios se reflejan en tiempo real
                    </p>
                  </div>
                </div>

                <div className="text-center">
                  {!googleDriveConnected ? (
                    <Button onClick={connectGoogleDrive} className="w-full md:w-auto">
                      <Cloud className="h-4 w-4 mr-2" />
                      Conectar con Google Drive
                    </Button>
                  ) : (
                    <div className="p-4 bg-green-50 rounded-lg border border-green-200">
                      <Check className="h-6 w-6 text-green-600 mx-auto mb-2" />
                      <p className="text-green-800 font-semibold">¡Google Drive Conectado!</p>
                      <p className="text-sm text-green-600">
                        Tus documentos se sincronizarán automáticamente
                      </p>
                    </div>
                  )}
                </div>

                <div className="text-center">
                  <Button variant="ghost" onClick={handleNext}>
                    Omitir por ahora
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Step 3: Signature Provider */}
          {currentStep === 3 && (
            <Card>
              <CardContent className="space-y-6 pt-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div 
                    className={`p-4 border-2 rounded-lg cursor-pointer transition-colors ${
                      signatureProvider === 'docusign' 
                        ? 'border-blue-500 bg-blue-50' 
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                    onClick={() => setSignatureProvider('docusign')}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-semibold">DocuSign</h3>
                      {signatureProvider === 'docusign' && <Check className="h-5 w-5 text-blue-600" />}
                    </div>
                    <p className="text-sm text-gray-600">
                      Líder mundial en firma electrónica
                    </p>
                    <Badge className="mt-2">Recomendado</Badge>
                  </div>

                  <div 
                    className={`p-4 border-2 rounded-lg cursor-pointer transition-colors ${
                      signatureProvider === 'adobe' 
                        ? 'border-blue-500 bg-blue-50' 
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                    onClick={() => setSignatureProvider('adobe')}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-semibold">Adobe Sign</h3>
                      {signatureProvider === 'adobe' && <Check className="h-5 w-5 text-blue-600" />}
                    </div>
                    <p className="text-sm text-gray-600">
                      Solución completa de documentos digitales
                    </p>
                  </div>

                  <div 
                    className={`p-4 border-2 rounded-lg cursor-pointer transition-colors ${
                      signatureProvider === 'signaturit' 
                        ? 'border-blue-500 bg-blue-50' 
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                    onClick={() => setSignatureProvider('signaturit')}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-semibold">Signaturit</h3>
                      {signatureProvider === 'signaturit' && <Check className="h-5 w-5 text-blue-600" />}
                    </div>
                    <p className="text-sm text-gray-600">
                      Proveedor europeo de confianza
                    </p>
                  </div>

                  <div 
                    className={`p-4 border-2 rounded-lg cursor-pointer transition-colors ${
                      signatureProvider === 'none' 
                        ? 'border-blue-500 bg-blue-50' 
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                    onClick={() => setSignatureProvider('none')}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-semibold">Configurar más tarde</h3>
                      {signatureProvider === 'none' && <Check className="h-5 w-5 text-blue-600" />}
                    </div>
                    <p className="text-sm text-gray-600">
                      Puedes configurar esto en cualquier momento
                    </p>
                  </div>
                </div>

                <div className="p-4 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-600">
                    <strong>Nota:</strong> Podrás cambiar o configurar adicionales proveedores 
                    de firma desde la configuración en cualquier momento.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Step 4: Features Overview */}
          {currentStep === 4 && (
            <Card>
              <CardContent className="space-y-6 pt-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-4">
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                        <FileText className="h-5 w-5 text-blue-600" />
                      </div>
                      <div>
                        <h3 className="font-semibold">Gestión Documental</h3>
                        <p className="text-sm text-gray-600">
                          Organiza, categoriza y gestiona todos tus documentos en un solo lugar
                        </p>
                      </div>
                    </div>

                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                        <Bot className="h-5 w-5 text-purple-600" />
                      </div>
                      <div>
                        <h3 className="font-semibold">Agentes de IA</h3>
                        <p className="text-sm text-gray-600">
                          Automatiza tareas repetitivas con asistentes inteligentes
                        </p>
                      </div>
                    </div>

                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                        <Search className="h-5 w-5 text-green-600" />
                      </div>
                      <div>
                        <h3 className="font-semibold">Búsqueda Semántica</h3>
                        <p className="text-sm text-gray-600">
                          Encuentra documentos por contenido, no solo por nombre
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center">
                        <PenTool className="h-5 w-5 text-orange-600" />
                      </div>
                      <div>
                        <h3 className="font-semibold">Firma Digital</h3>
                        <p className="text-sm text-gray-600">
                          Firma y solicita firmas de documentos de forma segura
                        </p>
                      </div>
                    </div>

                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center">
                        <Shield className="h-5 w-5 text-red-600" />
                      </div>
                      <div>
                        <h3 className="font-semibold">Seguridad Avanzada</h3>
                        <p className="text-sm text-gray-600">
                          Protección de datos con estándares enterprise
                        </p>
                      </div>
                    </div>

                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 bg-yellow-100 rounded-lg flex items-center justify-center">
                        <Zap className="h-5 w-5 text-yellow-600" />
                      </div>
                      <div>
                        <h3 className="font-semibold">Integrations</h3>
                        <p className="text-sm text-gray-600">
                          Conecta con tus herramientas favoritas
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <Separator />

                <div className="text-center">
                  <div className="w-20 h-20 mx-auto mb-6 bg-blue-100 rounded-full flex items-center justify-center">
                    <Shield className="h-10 w-10 text-blue-600" />
                  </div>
                  <h3 className="text-2xl font-bold text-gray-900 mb-4">¡Último paso: Selecciona tu Plan!</h3>
                  <p className="text-gray-600 mb-6 text-lg">
                    Para acceder a todas las funcionalidades de Nexus, necesitas seleccionar un plan de suscripción.
                    Elige el que mejor se adapte a las necesidades de tu empresa.
                  </p>
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                    <p className="text-blue-800 text-sm">
                      <strong>¿Por qué necesitas una suscripción?</strong><br/>
                      Nexus es una plataforma empresarial con IA avanzada que requiere recursos significativos para procesar documentos, 
                      ejecutar agentes inteligentes y mantener la seguridad de tus datos.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Navigation Buttons */}
        <div className="flex justify-between pt-6 border-t">
          <Button
            variant="outline"
            onClick={handlePrevious}
            disabled={currentStep <= 1}
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Anterior
          </Button>

          <Button
            onClick={handleNext}
            disabled={!canProceed()}
          >
            {currentStep === steps.length - 1 ? (
              'Continuar al Pago →'
            ) : (
              <>
                Siguiente
                <ArrowRight className="h-4 w-4 ml-2" />
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}