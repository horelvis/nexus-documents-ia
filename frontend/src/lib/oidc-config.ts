/**
 * OIDC Configuration for Emma On-Premise
 *
 * Configures KeyCloak as the identity provider.
 * These values can be overridden with environment variables.
 */

// Runtime config - reads from environment variables
function getEnvConfig() {
  // Read from environment variables with fallbacks
  const issuer = process.env.NEXT_PUBLIC_SSO_AUTHORITY || 'https://nouxcubeai.ddns.net:8085/realms/nouxcube'
  const clientId = process.env.NEXT_PUBLIC_SSO_CLIENT_ID || 'nouxcube-frontend'

  const defaults = {
    issuer,
    clientId,
    redirectUri: process.env.NEXT_PUBLIC_SSO_REDIRECT_URI || 'https://nouxcubeai.ddns.net/auth/callback',
    postLogoutRedirectUri: process.env.NEXT_PUBLIC_SSO_POST_LOGOUT_REDIRECT_URI || 'https://nouxcubeai.ddns.net',
  }

  // In browser, use window origin for redirect URIs if not specified
  // Force HTTPS to avoid mixed-content issues (required for Microsoft OAuth, KeyCloak HTTPS clients)
  if (typeof window !== 'undefined') {
    const origin = window.location.origin.replace(/^http:\/\//, 'https://')
    if (!process.env.NEXT_PUBLIC_SSO_REDIRECT_URI) {
      defaults.redirectUri = `${origin}/auth/callback`
    }
    if (!process.env.NEXT_PUBLIC_SSO_POST_LOGOUT_REDIRECT_URI) {
      defaults.postLogoutRedirectUri = `${origin}/auth/sign-in`
    }
  }

  return defaults
}

export const OIDC_CONFIG = {
  // KeyCloak server URL - from environment variable NEXT_PUBLIC_SSO_AUTHORITY
  get issuer() {
    return getEnvConfig().issuer
  },

  // Client credentials
  get clientId() {
    return getEnvConfig().clientId
  },

  // Client secret (optional for public clients)
  clientSecret: '',

  // Scopes
  scope: 'openid profile email',

  // Response type for Authorization Code flow
  responseType: 'code',

  // Redirect URIs - computed at runtime to use correct origin
  get redirectUri() {
    return getEnvConfig().redirectUri
  },

  get postLogoutRedirectUri() {
    return getEnvConfig().postLogoutRedirectUri
  },

  // Authorization endpoint — browser navigates here (KeyCloak handles HTTPS→HTTP redirect)
  get authorizationEndpoint() {
    return `${this.issuer}/protocol/openid-connect/auth`
  },

  // Token, userinfo, logout — called directly to KeyCloak (HTTPS, no proxy needed)
  get tokenEndpoint() {
    return `${this.issuer}/protocol/openid-connect/token`
  },

  get userinfoEndpoint() {
    return `${this.issuer}/protocol/openid-connect/userinfo`
  },

  get endSessionEndpoint() {
    return `${this.issuer}/protocol/openid-connect/logout`
  },

  get jwksUri() {
    return `${this.issuer}/protocol/openid-connect/certs`
  },
}

/**
 * Generate a random state parameter for CSRF protection
 */
export function generateState(): string {
  const array = new Uint8Array(32)
  crypto.getRandomValues(array)
  return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('')
}

/**
 * Generate PKCE code verifier
 */
export function generateCodeVerifier(): string {
  const array = new Uint8Array(32)
  crypto.getRandomValues(array)
  return base64UrlEncode(array)
}

/**
 * Generate PKCE code challenge from verifier
 * Uses Web Crypto API when available, falls back to pure JS SHA-256
 */
export async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(verifier)

  // Check if Web Crypto API is available (requires secure context)
  if (typeof crypto !== 'undefined' && crypto.subtle) {
    try {
      const digest = await crypto.subtle.digest('SHA-256', data)
      return base64UrlEncode(new Uint8Array(digest))
    } catch {
      // Fall through to JS implementation
    }
  }

  // Fallback: Pure JS SHA-256 for non-secure contexts (dev only)
  const hash = sha256(data)
  return base64UrlEncode(hash)
}

/**
 * Pure JavaScript SHA-256 implementation (fallback for non-secure contexts)
 */
function sha256(data: Uint8Array): Uint8Array {
  const K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
  ])

  let H = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
  ])

  const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n))
  const ch = (x: number, y: number, z: number) => (x & y) ^ (~x & z)
  const maj = (x: number, y: number, z: number) => (x & y) ^ (x & z) ^ (y & z)
  const sig0 = (x: number) => rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22)
  const sig1 = (x: number) => rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25)
  const gam0 = (x: number) => rotr(x, 7) ^ rotr(x, 18) ^ (x >>> 3)
  const gam1 = (x: number) => rotr(x, 17) ^ rotr(x, 19) ^ (x >>> 10)

  // Padding
  const msgLen = data.length
  const bitLen = msgLen * 8
  const padLen = ((msgLen + 8) % 64 === 0) ? 64 : 64 - ((msgLen + 8) % 64)
  const padded = new Uint8Array(msgLen + padLen + 8)
  padded.set(data)
  padded[msgLen] = 0x80
  const view = new DataView(padded.buffer)
  view.setUint32(padded.length - 4, bitLen, false)

  // Process blocks
  for (let i = 0; i < padded.length; i += 64) {
    const W = new Uint32Array(64)
    for (let t = 0; t < 16; t++) {
      W[t] = view.getUint32(i + t * 4, false)
    }
    for (let t = 16; t < 64; t++) {
      W[t] = (gam1(W[t-2]) + W[t-7] + gam0(W[t-15]) + W[t-16]) >>> 0
    }

    let [a, b, c, d, e, f, g, h] = H
    for (let t = 0; t < 64; t++) {
      const T1 = (h + sig1(e) + ch(e, f, g) + K[t] + W[t]) >>> 0
      const T2 = (sig0(a) + maj(a, b, c)) >>> 0
      h = g; g = f; f = e; e = (d + T1) >>> 0
      d = c; c = b; b = a; a = (T1 + T2) >>> 0
    }
    H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0
    H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0
    H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0
    H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0
  }

  const result = new Uint8Array(32)
  const resultView = new DataView(result.buffer)
  for (let i = 0; i < 8; i++) {
    resultView.setUint32(i * 4, H[i], false)
  }
  return result
}

/**
 * Base64 URL encode (for PKCE)
 */
function base64UrlEncode(buffer: Uint8Array): string {
  const base64 = btoa(String.fromCharCode(...buffer))
  return base64
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

/**
 * Build the authorization URL
 */
export async function buildAuthorizationUrl(): Promise<{ url: string; state: string; codeVerifier: string }> {
  const state = generateState()
  const codeVerifier = generateCodeVerifier()
  const codeChallenge = await generateCodeChallenge(codeVerifier)

  const params = new URLSearchParams({
    client_id: OIDC_CONFIG.clientId,
    redirect_uri: OIDC_CONFIG.redirectUri,
    response_type: OIDC_CONFIG.responseType,
    scope: OIDC_CONFIG.scope,
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  })

  return {
    url: `${OIDC_CONFIG.authorizationEndpoint}?${params.toString()}`,
    state,
    codeVerifier,
  }
}

/**
 * Exchange authorization code for tokens
 */
export async function exchangeCodeForTokens(
  code: string,
  codeVerifier: string
): Promise<{
  access_token: string
  refresh_token?: string
  id_token?: string
  expires_in: number
  token_type: string
}> {
  const response = await fetch(OIDC_CONFIG.tokenEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: OIDC_CONFIG.clientId,
      client_secret: OIDC_CONFIG.clientSecret,
      code,
      redirect_uri: OIDC_CONFIG.redirectUri,
      code_verifier: codeVerifier,
    }),
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Token exchange failed: ${error}`)
  }

  return response.json()
}

/**
 * Refresh access token
 */
export async function refreshAccessToken(refreshToken: string): Promise<{
  access_token: string
  refresh_token?: string
  expires_in: number
}> {
  const response = await fetch(OIDC_CONFIG.tokenEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      grant_type: 'refresh_token',
      client_id: OIDC_CONFIG.clientId,
      client_secret: OIDC_CONFIG.clientSecret,
      refresh_token: refreshToken,
    }),
  })

  if (!response.ok) {
    throw new Error('Token refresh failed')
  }

  return response.json()
}

/**
 * Get user info from OIDC provider
 */
export async function getUserInfo(accessToken: string): Promise<{
  sub: string
  email?: string
  email_verified?: boolean
  name?: string
  preferred_username?: string
  given_name?: string
  family_name?: string
}> {
  const response = await fetch(OIDC_CONFIG.userinfoEndpoint, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })

  if (!response.ok) {
    throw new Error('Failed to get user info')
  }

  return response.json()
}

/**
 * Build logout URL
 */
export function buildLogoutUrl(idToken?: string): string {
  const params = new URLSearchParams({
    post_logout_redirect_uri: OIDC_CONFIG.postLogoutRedirectUri,
    client_id: OIDC_CONFIG.clientId,
  })

  if (idToken) {
    params.set('id_token_hint', idToken)
  }

  return `${OIDC_CONFIG.endSessionEndpoint}?${params.toString()}`
}
