// frontend/app/routes/dashboard+/settings.index.tsx - Con tipos TypeScript corregidos
import type { LoaderFunctionArgs, ActionFunctionArgs } from '@remix-run/node'
import { json, redirect } from '@remix-run/node'
import { useLoaderData, useActionData, Link } from '@remix-run/react'
import { getAuth } from '@clerk/remix/ssr.server'
import { z } from 'zod'
import { getZodConstraint, parseWithZod } from '@conform-to/zod'
import { getFormProps, getInputProps, useForm } from '@conform-to/react'
import { AuthenticityTokenInput } from 'remix-utils/csrf/react'
import { HoneypotInputs } from 'remix-utils/honeypot/react'
import { 
  Trash2, 
  AlertTriangle, 
  ExternalLink, 
  User, 
  Mail, 
  Calendar,
  Settings,
  Camera
} from 'lucide-react'

import { createApiService } from '#app/utils/backend.server'
import { validateCSRF } from '#app/utils/csrf.server'
import { checkHoneypot } from '#app/utils/honeypot.server'
import { createToastHeaders } from '#app/utils/toast.server'
import { useDoubleCheck } from '#app/utils/hooks/use-double-check'
import { useIsPending } from '#app/utils/misc'
import { Button } from '#app/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '#app/components/ui/card'
import { Input } from '#app/components/ui/input'
import { Label } from '#app/components/ui/label'
import { Separator } from '#app/components/ui/separator'
import { Badge } from '#app/components/ui/badge'

// ✅ Definir tipos para el backend user
interface BackendUser {
  id: string
  username?: string
  email?: string
  roles?: Array<{ id: string; name: string }>
  createdAt?: string
  updatedAt?: string
}

// ✅ Definir tipos para el loader data
interface LoaderData {
  backendUser: BackendUser | null
  backendConnected: boolean
  error: string | null
  clerkUserId: string
}

const UsernameSchema = z.object({
  username: z
    .string()
    .min(3, 'Username debe tener al menos 3 caracteres')
    .max(20, 'Username no puede tener más de 20 caracteres')
    .toLowerCase()
    .trim()
    .regex(/^[a-zA-Z0-9_]+$/, 'Username solo puede contener letras, números y guiones bajos'),
})

const DeleteAccountSchema = z.object({
  confirmText: z.string().refine(val => val === 'DELETE', {
    message: 'Debe escribir "DELETE" para confirmar'
  })
})

export async function loader(args: LoaderFunctionArgs) {
  const {request } = args
  const { userId } = await getAuth(args)
  
  if (!userId) {
    return redirect('/auth/sign-in')
  }

  // Intentar obtener datos del backend
  let backendUser: BackendUser | null = null
  let backendConnected = false
  let error: string | null = null

  try {
    const apiService = await createApiService(args)
    const userData = await apiService.getCurrentUser()
    backendUser = userData as BackendUser
    backendConnected = true
  } catch (err) {
    console.error('Error loading user from backend:', err)
    error = err instanceof Error ? err.message : 'Error desconocido'
    backendConnected = false
  }

  return json<LoaderData>({
    backendUser,
    backendConnected,
    error,
    clerkUserId: userId
  })
}

export async function action(args: ActionFunctionArgs) {

  const {request } = args
  const { userId } = await getAuth(args)
  
  if (!userId) {
    return redirect('/auth/sign-in')
  }

  const clonedRequest = request.clone()
  const formData = await clonedRequest.formData()
  
  await validateCSRF(formData, clonedRequest.headers)
  checkHoneypot(formData)

  const intent = formData.get('intent')

  try {
    const apiService = await createApiService(args)

    if (intent === 'update-username') {
      const submission = parseWithZod(formData, { schema: UsernameSchema })
      
      if (submission.status !== 'success') {
        return json(submission.reply(), {
          status: submission.status === 'error' ? 400 : 200,
        })
      }

      await apiService.updateUser({
        username: submission.value.username
      })

      return json(submission.reply(), {
        headers: await createToastHeaders({
          title: 'Username actualizado',
          description: 'Tu nombre de usuario ha sido actualizado correctamente.',
          type: 'success',
        }),
      })
    }

    if (intent === 'delete-account') {
      const submission = parseWithZod(formData, { schema: DeleteAccountSchema })
      
      if (submission.status !== 'success') {
        return json(submission.reply(), {
          status: submission.status === 'error' ? 400 : 200,
        })
      }

      await apiService.deleteAccount()
      return redirect('/auth/sign-out?deleted=true')
    }

    return json({ error: 'Acción no válida' }, { status: 400 })

  } catch (error) {
    console.error('Error in settings action:', error)
    
    if (intent === 'update-username') {
      return json(
        { error: 'Error actualizando username. Inténtalo de nuevo.' },
        { 
          status: 500,
          headers: await createToastHeaders({
            title: 'Error',
            description: 'No se pudo actualizar el username. Inténtalo de nuevo.',
            type: 'error',
          }),
        }
      )
    }

    return json(
      { error: 'Error procesando la solicitud' },
      { status: 500 }
    )
  }
}

export default function SettingsGeneral() {
  // ✅ Usar tipos explícitos para el loader data
  const { backendUser, backendConnected, error } = useLoaderData<LoaderData>()
  const lastResult = useActionData<typeof action>()
  const isPending = useIsPending()
  const { doubleCheck, getButtonProps } = useDoubleCheck()

  const [usernameForm, usernameFields] = useForm({
    lastResult: lastResult?.intent === 'update-username' ? lastResult : undefined,
    constraint: getZodConstraint(UsernameSchema),
    onValidate({ formData }) {
      return parseWithZod(formData, { schema: UsernameSchema })
    },
  })

  const [deleteForm, deleteFields] = useForm({
    lastResult: lastResult?.intent === 'delete-account' ? lastResult : undefined,
    constraint: getZodConstraint(DeleteAccountSchema),
    onValidate({ formData }) {
      return parseWithZod(formData, { schema: DeleteAccountSchema })
    },
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-primary">Configuración General</h1>
        <p className="text-muted-foreground">
          Gestiona tu perfil y configuración de cuenta
        </p>
      </div>

      {/* Estado de conectividad */}
      {!backendConnected && (
        <Card className="border-yellow-200 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-900/20">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-yellow-700 dark:text-yellow-400">
              <AlertTriangle className="h-5 w-5" />
              Modo sin conexión
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-yellow-600 dark:text-yellow-300">
              Algunas configuraciones pueden no estar disponibles. Los datos de Clerk siguen funcionando.
            </p>
            {error && (
              <p className="mt-2 text-xs text-yellow-500">
                Error técnico: {error}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Enlaces a Clerk User Profile */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            Perfil de Usuario (Clerk)
          </CardTitle>
          <CardDescription>
            Gestiona tu perfil, foto, y datos personales de forma segura con Clerk
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <Button asChild variant="outline" className="h-auto p-4">
                <a href="/user-profile" target="_blank" rel="noopener noreferrer">
                  <div className="flex items-center gap-3 w-full">
                    <Camera className="h-5 w-5 text-blue-500" />
                    <div className="text-left">
                      <p className="font-medium">Perfil y Foto</p>
                      <p className="text-xs text-muted-foreground">
                        Actualizar foto, nombre y datos personales
                      </p>
                    </div>
                    <ExternalLink className="h-4 w-4 ml-auto" />
                  </div>
                </a>
              </Button>

              <Button asChild variant="outline" className="h-auto p-4">
                <a href="/user-profile/security" target="_blank" rel="noopener noreferrer">
                  <div className="flex items-center gap-3 w-full">
                    <Settings className="h-5 w-5 text-green-500" />
                    <div className="text-left">
                      <p className="font-medium">Seguridad</p>
                      <p className="text-xs text-muted-foreground">
                        Contraseña, 2FA y configuración de seguridad
                      </p>
                    </div>
                    <ExternalLink className="h-4 w-4 ml-auto" />
                  </div>
                </a>
              </Button>
            </div>

            <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md">
              <p className="text-sm text-blue-700 dark:text-blue-300">
                <strong>Nota:</strong> Los enlaces te llevarán a páginas seguras de Clerk donde podrás 
                gestionar todos los aspectos de tu perfil. Los cambios se sincronizan automáticamente.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Username del Backend */}
      {backendConnected && backendUser && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mail className="h-5 w-5" />
              Username del Sistema
            </CardTitle>
            <CardDescription>
              Username específico para el sistema interno (diferente del perfil de Clerk)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form {...getFormProps(usernameForm)} method="post" className="space-y-4">
              <AuthenticityTokenInput />
              <HoneypotInputs />
              <input type="hidden" name="intent" value="update-username" />
              
              <div className="space-y-2">
                <Label htmlFor={usernameFields.username.id}>Username del Sistema</Label>
                <Input
                  {...getInputProps(usernameFields.username, { type: 'text' })}
                  placeholder="username_sistema"
                  defaultValue={backendUser.username || ''}
                  className={usernameFields.username.errors ? 'border-destructive' : ''}
                />
                {usernameFields.username.errors && (
                  <p className="text-sm text-destructive">
                    {usernameFields.username.errors.join(' ')}
                  </p>
                )}
                <p className="text-xs text-muted-foreground">
                  Este username se usa para funciones internas del sistema
                </p>
              </div>

              <Button 
                type="submit" 
                disabled={isPending}
                size="sm"
              >
                {isPending ? 'Actualizando...' : 'Actualizar Username'}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Información de la cuenta */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5" />
            Información de la Cuenta
          </CardTitle>
          <CardDescription>
            Detalles sobre tu cuenta y estado
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label className="text-sm font-medium">Estado de Datos</Label>
              <div className="flex items-center gap-2">
                <Badge variant="default">
                  Clerk: Conectado
                </Badge>
                <Badge variant={backendConnected ? 'default' : 'destructive'}>
                  Backend: {backendConnected ? 'Conectado' : 'Desconectado'}
                </Badge>
              </div>
            </div>

            {backendUser && (
              <div className="space-y-2">
                <Label className="text-sm font-medium">Usuario del Sistema</Label>
                <p className="text-sm text-muted-foreground">
                  ID: {backendUser.id}
                </p>
                <p className="text-sm text-muted-foreground">
                  Roles: {backendUser.roles?.map((r) => r.name).join(', ') || 'user'}
                </p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Separator />

      {/* Zona de peligro */}
      <Card className="border-destructive">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <Trash2 className="h-5 w-5" />
            Zona de Peligro
          </CardTitle>
          <CardDescription>
            Acciones irreversibles para tu cuenta
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {backendConnected ? (
              <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4">
                <h3 className="font-medium text-destructive">Eliminar Cuenta</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Esto eliminará permanentemente tu cuenta, todos los datos asociados y el acceso a la plataforma. 
                  Esta acción no se puede deshacer.
                </p>
                
                <form {...getFormProps(deleteForm)} method="post" className="mt-4 space-y-3">
                  <AuthenticityTokenInput />
                  <HoneypotInputs />
                  <input type="hidden" name="intent" value="delete-account" />
                  
                  <div className="space-y-2">
                    <Label htmlFor={deleteFields.confirmText.id} className="text-sm">
                      Escribe <code className="font-mono text-xs bg-muted px-1 py-0.5 rounded">DELETE</code> para confirmar:
                    </Label>
                    <Input
                      {...getInputProps(deleteFields.confirmText, { type: 'text' })}
                      placeholder="DELETE"
                      className={deleteFields.confirmText.errors ? 'border-destructive' : ''}
                    />
                    {deleteFields.confirmText.errors && (
                      <p className="text-sm text-destructive">
                        {deleteFields.confirmText.errors.join(' ')}
                      </p>
                    )}
                  </div>

                  <Button
                    type="submit"
                    variant="destructive"
                    size="sm"
                    disabled={isPending}
                    {...getButtonProps()}
                  >
                    {doubleCheck ? '¿Estás seguro?' : 'Eliminar Cuenta'}
                  </Button>
                </form>
              </div>
            ) : (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <p className="text-sm text-gray-600">
                  Las acciones de eliminación de cuenta requieren conexión al backend.
                </p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}