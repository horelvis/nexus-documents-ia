/**
 * Permissions and Roles.
 * Implementation based on github.com/epicweb-dev/epic-stack
 */
import { userHasRole } from '#app/utils/misc'
import { AUTH_ROUTES } from '#app/utils/constants/auth'


export type RoleName = 'user' | 'admin'

export async function requireUserWithRole(request: Request, name: RoleName) {
  const user = await requireUser(request, { redirectTo: AUTH_ROUTES.SIGN_IN })
  const hasRole = userHasRole(user, name)
  if (!hasRole) {
    throw Response.json(
      {
        error: 'Unauthorized',
        requiredRole: name,
        message: `Unauthorized: required role: ${name}`,
      },
      { status: 403 },
    )
  }
  return user
}
