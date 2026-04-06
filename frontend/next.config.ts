import type { NextConfig } from "next"
import path from "path"

const nextConfig: NextConfig = {
  transpilePackages: ["framer-motion"],

  // Force single React instance across monorepo (works with both npm and pnpm)
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      react: path.dirname(require.resolve("react/package.json")),
      "react-dom": path.dirname(require.resolve("react-dom/package.json")),
    }
    return config
  },

  // Exclude LangChain packages from server-side bundling (SSR).
  // They import React hooks that conflict with Next.js DevTools' segment-explorer
  // when bundled into the SSR layer. These packages are client-only (useStream).
  serverExternalPackages: [
    "@langchain/langgraph-sdk",
    "@langchain/core",
  ],

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
    // Server-side runtime env vars for rewrite destination.
    // Priority: BACKEND_URL > API_BASE_URL > NEXT_PUBLIC_BACKEND_URL > fallback
    const backendUrl = process.env.BACKEND_URL ||
                       process.env.API_BASE_URL ||
                       process.env.NEXT_PUBLIC_BACKEND_URL ||
                       process.env.NEXT_PUBLIC_API_URL?.replace(/\/api\/v1\/?$/, '') ||
                       "http://localhost:8000"

    console.log(`[Next.js Rewrites] Backend URL: ${backendUrl}`)

    return [
      // LangGraph SDK endpoints (threads, assistants, runs)
      {
        source: "/api/threads/:path*",
        destination: `${backendUrl}/api/threads/:path*`,
      },
      {
        source: "/api/threads",
        destination: `${backendUrl}/api/threads`,
      },
      {
        source: "/api/assistants/:path*",
        destination: `${backendUrl}/api/assistants/:path*`,
      },
      // General API proxy
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ]
  },
}

export default nextConfig
