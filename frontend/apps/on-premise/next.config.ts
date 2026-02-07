import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  transpilePackages: ["@nexus/shared", "framer-motion"],

  // Enable standalone output for Docker deployments
  output: "standalone",

  // Disable x-powered-by header for security
  poweredByHeader: false,

  // Rewrite API calls to backend and OIDC endpoints to KeyCloak
  async rewrites() {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ||
                       process.env.NEXT_PUBLIC_API_URL?.replace(/\/api\/v1\/?$/, '') ||
                       "http://localhost:8000"

    // KeyCloak issuer URL (HTTP internal) — proxied through HTTPS frontend to avoid mixed content
    const keycloakUrl = process.env.NEXT_PUBLIC_SSO_AUTHORITY || "http://nouxcube.local.es:8085/realms/nouxcube"

    console.log(`[Next.js Rewrites] Backend URL: ${backendUrl}`)
    console.log(`[Next.js Rewrites] KeyCloak URL: ${keycloakUrl}`)

    // Emma Agent Service URL (internal HTTP, proxied through HTTPS frontend)
    const emmaServiceUrl = process.env.EMMA_SERVICE_URL || "http://localhost:8009"
    console.log(`[Next.js Rewrites] Emma Service URL: ${emmaServiceUrl}`)

    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
      // Proxy OIDC endpoints through HTTPS frontend → HTTP KeyCloak (avoids mixed content)
      {
        source: "/oidc/:path*",
        destination: `${keycloakUrl}/protocol/openid-connect/:path*`,
      },
      // Proxy Emma notification endpoints through HTTPS frontend → HTTP Emma Service (avoids mixed content)
      {
        source: "/emma/notifications/:path*",
        destination: `${emmaServiceUrl}/emma/notifications/:path*`,
      },
    ]
  },
}

export default nextConfig
