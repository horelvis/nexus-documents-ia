'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useUserContext } from '@/contexts/user-context'
import { 
  ArrowRight,
  CheckCircle, 
  Loader2,
  Building,
  CreditCard,
  User
} from 'lucide-react'

// Schema simplificado - solo lo esencial
const onboardingSchema = z.object({
  firstName: z.string().min(2, "El nombre debe tener al menos 2 caracteres"),
  lastName: z.string().min(2, "El apellido debe tener al menos 2 caracteres"),
  companyName: z.string().min(2, "El nombre de la empresa es requerido"),
  cif: z.string().min(8, "El CIF debe tener al menos 8 caracteres"),
})

type OnboardingFormData = z.infer<typeof onboardingSchema>

interface SimplifiedOnboardingProps {
  onComplete?: (tenantId?: string) => void
  /** Datos del checkout de Stripe si viene de pago */
  checkoutData?: {
    plan_id: string
    customer_email: string
    amount_total: number
    currency: string
  } | null
  /** Si es true, muestra que viene de un pago exitoso */
  isPostPayment?: boolean
}

export function SimplifiedOnboarding({ 
  onComplete, 
  checkoutData, 
  isPostPayment = false 
}: SimplifiedOnboardingProps) {
  const router = useRouter()
  const { 
    clerkUser, 
    markOnboardingComplete,
    backendUser,
    refetchUser
  } = useUserContext()

  const [isProcessing, setIsProcessing] = useState(false)

  const form = useForm<OnboardingFormData>({
    resolver: zodResolver(onboardingSchema),
    defaultValues: {
      firstName: clerkUser?.firstName || '',
      lastName: clerkUser?.lastName || '',
      companyName: '',
      cif: '',
    }
  })

  const handleSubmit = async (data: OnboardingFormData) => {
    try {
      setIsProcessing(true)
      
      // Datos mínimos para el onboarding
      const onboardingData = {
        first_name: data.firstName,
        last_name: data.lastName,
        company_name: data.companyName,
        cif: data.cif,
        selected_plan: checkoutData?.plan_id || 'free',
        onboarding_step: 'completed'
      }
      
      console.log('✅ Completing simplified onboarding:', onboardingData)
      
      const success = await markOnboardingComplete(onboardingData)
      if (!success) {
        throw new Error('Failed to complete onboarding')
      }
      
      // Refetch user data
      await refetchUser()
      
      // Redirigir al dashboard
      setTimeout(() => {
        handleGoToDashboard()
      }, 1000)
      
    } catch (error) {
      console.error('Error completing onboarding:', error)
      alert(`Error al completar la configuración: ${error.message}`)
    } finally {
      setIsProcessing(false)
    }
  }

  const handleGoToDashboard = () => {
    const tenantId = backendUser?.tenant_id
    
    if (onComplete) {
      onComplete(tenantId)
    } else {
      if (tenantId) {
        router.push(`/${tenantId}/dashboard`)
      } else {
        router.push('/dashboard')
      }
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl md:text-4xl font-bold mb-4 bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            {isPostPayment ? '¡Pago Completado!' : '¡Bienvenido a Nexus!'}
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-300 max-w-2xl mx-auto mb-6">
            {isPostPayment 
              ? 'Tu suscripción está activa. Solo necesitamos algunos datos para la facturación.'
              : 'Completa tu perfil para comenzar a usar Nexus'
            }
          </p>

          {/* Mostrar datos del pago si aplica */}
          {checkoutData && (
            <div className="max-w-md mx-auto mb-6">
              <Card className="bg-green-50 border-green-200">
                <CardContent className="pt-4">
                  <div className="flex items-center space-x-2 text-green-700">
                    <CheckCircle className="h-5 w-5" />
                    <span className="font-medium">
                      Suscripción {checkoutData.plan_id} activada
                    </span>
                  </div>
                  <p className="text-sm text-green-600 mt-1">
                    {(checkoutData.amount_total / 100).toFixed(2)} {checkoutData.currency.toUpperCase()}
                  </p>
                </CardContent>
              </Card>
            </div>
          )}
        </div>

        {/* Formulario unificado */}
        <div className="max-w-2xl mx-auto">
          <Card className="shadow-xl">
            <CardHeader className="text-center">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full mb-4">
                <User className="h-6 w-6 text-white" />
              </div>
              <CardTitle className="text-xl">Información de Facturación</CardTitle>
              <CardDescription>
                Solo necesitamos estos datos para generar tus facturas correctamente
              </CardDescription>
            </CardHeader>
            
            <CardContent>
              <Form {...form}>
                <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
                  
                  {/* Datos personales */}
                  <div className="space-y-4">
                    <div className="flex items-center space-x-2 mb-3">
                      <User className="h-4 w-4 text-gray-500" />
                      <h3 className="font-medium text-gray-900 dark:text-gray-100">Datos Personales</h3>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <FormField
                        control={form.control}
                        name="firstName"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Nombre *</FormLabel>
                            <FormControl>
                              <Input placeholder="Tu nombre" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      
                      <FormField
                        control={form.control}
                        name="lastName"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Apellidos *</FormLabel>
                            <FormControl>
                              <Input placeholder="Tus apellidos" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                  </div>

                  {/* Datos de empresa */}
                  <div className="space-y-4 border-t pt-6">
                    <div className="flex items-center space-x-2 mb-3">
                      <Building className="h-4 w-4 text-gray-500" />
                      <h3 className="font-medium text-gray-900 dark:text-gray-100">Datos de Facturación</h3>
                    </div>
                    
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

                  {/* Botón de envío */}
                  <div className="pt-6 border-t">
                    <Button 
                      type="submit"
                      disabled={isProcessing}
                      className="w-full bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white"
                      size="lg"
                    >
                      {isProcessing ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin mr-2" />
                          Completando configuración...
                        </>
                      ) : (
                        <>
                          Finalizar Configuración
                          <ArrowRight className="h-4 w-4 ml-2" />
                        </>
                      )}
                    </Button>
                  </div>

                  {isPostPayment && (
                    <div className="text-center text-sm text-gray-500">
                      <p>Los datos de facturación se sincronizarán con Stripe automáticamente</p>
                    </div>
                  )}
                </form>
              </Form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

export default SimplifiedOnboarding