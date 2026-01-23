import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  transpilePackages: ["@nexus/shared"],

  // Enable standalone output for Docker deployments
  output: "standalone",

  // Disable x-powered-by header for security
  poweredByHeader: false,

  // Rewrite API calls to backend
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiUrl}/api/v1/:path*`,
      },
    ]
  },
}

export default nextConfig
