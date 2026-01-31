import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  transpilePackages: ["@nexus/shared", "framer-motion"],

  // Enable standalone output for Docker deployments
  output: "standalone",

  // Disable x-powered-by header for security
  poweredByHeader: false,

  // Rewrite API calls to backend
  async rewrites() {
    // For rewrites, prefer NEXT_PUBLIC_BACKEND_URL (internal network) over NEXT_PUBLIC_API_URL
    // This avoids DNS resolution issues when running locally
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ||
                       process.env.NEXT_PUBLIC_API_URL?.replace(/\/api\/v1\/?$/, '') ||
                       "http://localhost:8000"

    console.log(`[Next.js Rewrites] Backend URL: ${backendUrl}`)

    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ]
  },
}

export default nextConfig
