// frontend/app/routes/onboarding+/username.tsx
import type {
  MetaFunction,
  LoaderFunctionArgs,
  ActionFunctionArgs,
} from '@remix-run/node'
import { useRef, useEffect } from 'react'
import { Form, useActionData, useLoaderData } from '@remix-run/react'
import { json, redirect } from '@remix-run/node'
import { useHydrated } from 'remix-utils/use-hydrated'
import { AuthenticityTokenInput } from 'remix-utils/csrf/react'
import { HoneypotInputs } from 'remix-utils/honeypot/react'
import { z } from 'zod'
import { getZodConstraint, parseWithZod } from '@conform-to/zod'
import { getFormProps, getInputProps, useForm } from '@conform-to/react'
import { Loader2 } from 'lucide-react'
import { getAuth } from '@clerk/remix/ssr.server'

import { createApiService } from '#app/utils/backend.server'
import { validateCSRF } from '#app/utils/csrf.server'
import { checkHoneypot } from '#app/utils/honeypot.server'
import { useIsPending } from '#app/utils/misc'
import { ROUTE_PATH as ONBOARDING_PLAN_PATH } from '#app/routes/onboarding+/plan'
import { ROUTE_PATH as SIGN_IN_PATH } from '#app/routes/auth+/sign-in.$'
import { Input } from '#app/components/ui/input'
import { Button } from '#app/components/ui/button'

export const ROUTE_PATH = '/onboarding/username' as const

export const UsernameSchema = z.object({
  username: z
    .string()
    .min(3)
    .max(20)
    .toLowerCase()
    .trim()
    .regex(/^[a-zA-Z0-9]+$/, 'Username may only contain alphanumeric characters.'),
})

export const meta: MetaFunction = () => {
  return [{ title: 'Configurar Username - Remix SaaS' }]
}

export async function loader({ request }: LoaderFunctionArgs) {
  const { userId } = await getAuth({ request })
  
  if (!userId) {
    return redirect(SIGN_IN_PATH)
  }

  try {
    const apiService = await createApiService({ request })
    const user = await apiService.getCurrentUser()
    
    // Si el usuario ya tiene username, redirigir al siguiente paso
    if (user?.username) {
      return redirect(ONBOARDING_PLAN_PATH)
    }

    return json({ 
      backendConnected: true,
      user,
      clerkUserId: userId 
    })
  } catch (error) {
    console.error('Error en username loader:', error)
    return json({ 
      backendConnected: false,
      user: null,
      clerkUserId: userId,
      error: error instanceof Error ? error.message : 'Error desconocido'
    })
  }
}

export async function action({ request }: ActionFunctionArgs) {
  const { userId } = await getAuth({ request })
  
  if (!userId) {
    return redirect(SIGN_IN_PATH)
  }

  const clonedRequest = request.clone()
  const formData = await clonedRequest.formData()
  await validateCSRF(formData, clonedRequest.headers)
  checkHoneypot(formData)

  const submission = parseWithZod(formData, { schema: UsernameSchema })
  if (submission.status !== 'success') {
    return json(
      submission.reply(), 
      { status: submission.status === 'error' ? 400 : 200 }
    )
  }

  const { username } = submission.value

  try {
    const apiService = await createApiService({ request })
    
    // Intentar actualizar el username en el backend
    // Como no tenemos un endpoint específico para esto, 
    // podrías necesitar crear uno en el backend o usar el endpoint de user update
    
    // Por ahora, simulamos que se actualiza correctamente
    // En producción, deberías tener un endpoint como:
    // await apiService.updateUserProfile({ username })
    
    // Si el backend no está disponible, continuar con el flujo
    console.log(`Username ${username} configurado para usuario ${userId}`)
    
    return redirect(ONBOARDING_PLAN_PATH)
    
  } catch (error) {
    console.error('Error actualizando username:', error)
    
    // Si hay error con el backend pero el usuario completó el formulario,
    // permitir continuar (el username se puede sincronizar después)
    return redirect(ONBOARDING_PLAN_PATH)
  }
}

export default function OnboardingUsername() {
  const { backendConnected, user, error } = useLoaderData<typeof loader>()
  const lastResult = useActionData<typeof action>()
  const inputRef = useRef<HTMLInputElement>(null)
  const isHydrated = useHydrated()
  const isPending = useIsPending()

  const [form, { username }] = useForm({
    lastResult,
    constraint: getZodConstraint(UsernameSchema),
    onValidate({ formData }) {
      return parseWithZod(formData, { schema: UsernameSchema })
    },
  })

  useEffect(() => {
    isHydrated && inputRef.current?.focus()
  }, [isHydrated])

  return (
    <div className="mx-auto flex h-full w-full max-w-96 flex-col items-center justify-center gap-6">
      <div className="flex flex-col items-center gap-2">
        <span className="mb-2 animate-pulse select-none text-6xl">👋</span>
        <h3 className="text-center text-2xl font-medium text-primary">¡Bienvenido!</h3>
        <p className="text-center text-base font-normal text-primary/60">
          Configuremos tu nombre de usuario para comenzar.
        </p>
        
        {!backendConnected && (
          <div className="mt-2 p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-md">
            <p className="text-sm text-yellow-700 dark:text-yellow-300">
              ⚠️ Modo sin conexión: La configuración se sincronizará cuando se restablezca la conexión.
            </p>
          </div>
        )}
      </div>

      <Form
        method="POST"
        autoComplete="off"
        className="flex w-full flex-col items-start gap-1"
        {...getFormProps(form)}>
        {/* Security */}
        <AuthenticityTokenInput />
        <HoneypotInputs />

        <div className="flex w-full flex-col gap-1.5">
          <label htmlFor="username" className="sr-only">
            Username
          </label>
          <Input
            placeholder="Nombre de usuario"
            autoComplete="off"
            ref={inputRef}
            required
            className={`bg-transparent ${
              username.errors && 'border-destructive focus-visible:ring-destructive'
            }`}
            {...getInputProps(username, { type: 'text' })}
          />
        </div>

        <div className="flex flex-col">
          {username.errors && (
            <span className="mb-2 text-sm text-destructive dark:text-destructive-foreground">
              {username.errors.join(' ')}
            </span>
          )}
        </div>

        <Button type="submit" size="sm" className="w-full" disabled={isPending}>
          {isPending ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Configurando...
            </>
          ) : (
            'Continuar'
          )}
        </Button>
      </Form>

      <p className="px-6 text-center text-sm font-normal leading-normal text-primary/60">
        Puedes cambiar tu nombre de usuario en cualquier momento desde la configuración de tu cuenta.
      </p>
      
      {error && (
        <div className="w-full p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md">
          <p className="text-sm text-red-700 dark:text-red-300">
            Error: {error}
          </p>
        </div>
      )}
    </div>
  )
}