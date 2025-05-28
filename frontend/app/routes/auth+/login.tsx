import {
  redirect,
  MetaFunction,
  LoaderFunctionArgs,
  ActionFunctionArgs,
} from '@remix-run/node'
import { useRef, useEffect } from 'react'
import { Form, useLoaderData, data } from '@remix-run/react'
import { useHydrated } from 'remix-utils/use-hydrated'
import { AuthenticityTokenInput } from 'remix-utils/csrf/react'
import { HoneypotInputs } from 'remix-utils/honeypot/react'
import { z } from 'zod'
import { getZodConstraint, parseWithZod } from '@conform-to/zod'
import { getFormProps, getInputProps, useForm } from '@conform-to/react'
import { Loader2 } from 'lucide-react'
import { authenticator } from '#app/modules/auth/auth.server'
import { getSession, commitSession } from '#app/modules/auth/auth-session.server'
import { validateCSRF } from '#app/utils/csrf.server'
import { checkHoneypot } from '#app/utils/honeypot.server'
import { useIsPending } from '#app/utils/misc'
import { siteConfig } from '#app/utils/constants/brand'

import { ROUTE_PATH as DASHBOARD_PATH } from '#app/routes/dashboard+/_layout'
import { ROUTE_PATH as AUTH_VERIFY_PATH } from '#app/routes/auth+/verify'
import { RedirectToSignIn, SignIn } from '@clerk/remix'
import { getAuth } from '@clerk/remix/ssr.server'
import { Theme } from '../../utils/hooks/use-theme';

export const ROUTE_PATH = '/auth/sign-in' as const

export const LoginSchema = z.object({
  email: z.string().max(256).email('Email address is not valid.'),
})

export const meta: MetaFunction = () => {
  return [{ title: `${siteConfig.siteTitle} - Login` }]
}

export async function loader(args: LoaderFunctionArgs) {

  const { userId } = await getAuth(args)

  // Si ya hay sesión activa, redirige a la página principal o dashboard
  if (userId) {
    return redirect(DASHBOARD_PATH)
  }

  const cookie = await getSession(args.request.headers.get('Cookie'))
  const authEmail = cookie.get('auth:email')
  const authError = cookie.get(authenticator.sessionErrorKey)

  return data(
    { authEmail, authError },
    { headers: { 'Set-Cookie': await commitSession(cookie) } },
  )
}

export async function action({ request }: ActionFunctionArgs) {
  const url = new URL(request.url)
  const pathname = url.pathname

  const clonedRequest = request.clone()
  const formData = await clonedRequest.formData()
  await validateCSRF(formData, clonedRequest.headers)
  checkHoneypot(formData)

  await authenticator.authenticate('TOTP', request, {
    successRedirect: AUTH_VERIFY_PATH,
    failureRedirect: pathname,
  })
}

export default function Login() {
  const { authEmail, authError } = useLoaderData<typeof loader>()
  const inputRef = useRef<HTMLInputElement>(null)
  const isHydrated = useHydrated()
  const isPending = useIsPending()

  useEffect(() => {
    isHydrated && inputRef.current?.focus()
  }, [isHydrated])

  return (
    <div className="mx-auto flex h-full w-full max-w-96 flex-col items-center justify-center gap-6">
      <div className="mb-2 flex flex-col gap-2">
        <h3 className="text-center text-2xl font-medium text-primary">
          Continue to Remix SaaS
        </h3>
        <p className="text-center text-base font-normal text-primary/60">
          Please log in to continue.
        </p>
      </div>

      <RedirectToSignIn />

      <p className="px-12 text-center text-sm font-normal leading-normal text-primary/60">
        By clicking continue, you agree to our{' '}
        <a href="/" className="underline hover:text-primary">
          Terms of Service
        </a>{' '}
        and{' '}
        <a href="/" className="underline hover:text-primary">
          Privacy Policy.
        </a>
      </p>
    </div>
  )
}
