import type { LoaderFunctionArgs } from '@remix-run/node'
import { authenticator } from '#app/modules/auth/auth.server'

import { ROUTE_PATH as DASHBOARD_PATH } from '#app/routes/dashboard+/_layout'

const SIGN_IN_PATH = '/auth/sign-in'

export const ROUTE_PATH = '/auth/magic-link' as const

export async function loader({ request }: LoaderFunctionArgs) {
  return authenticator.authenticate('TOTP', request, {
    successRedirect: DASHBOARD_PATH,
    failureRedirect: SIGN_IN_PATH,
  })
}
