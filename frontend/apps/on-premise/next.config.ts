import type { NextConfig } from "next"
import path from "path"

const nextConfig: NextConfig = {
  transpilePackages: ["@nexus/shared", "framer-motion"],

  // Force single React instance across monorepo (works with both npm and pnpm)
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      react: path.dirname(require.resolve("react/package.json")),
      "react-dom": path.dirname(require.resolve("react-dom/package.json")),
    }
    return config
  },

  // Enable standalone output for Docker deployments
  output: "standalone",

  // Disable x-powered-by header for security
  poweredByHeader: false,

  // Skip ESLint during production builds (linting runs in dev/CI instead)
  eslint: {
    ignoreDuringBuilds: true,
  },

  // Skip TypeScript type-checking during builds (type-check runs in dev/CI instead)
  typescript: {
    ignoreBuildErrors: true,
  },

  // Rewrite API calls to backend
  async rewrites() {
    // BACKEND_URL is a server-side runtime env var (set in Docker compose).
    // NEXT_PUBLIC_* vars are baked at build time and won't change in containers.
    const backendUrl = process.env.BACKEND_URL ||
                       process.env.NEXT_PUBLIC_BACKEND_URL ||
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
