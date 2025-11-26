import type { NextConfig } from "next";
// We need to use require for some webpack plugins if they don't have types or ESM support
// import webpack from 'webpack'; // If needed

const splitEnvList = (value?: string) =>
  value
    ? value
        .split(",")
        .map(entry => entry.trim())
        .filter(Boolean)
    : [];

const stripPort = (host: string) => host.split(":")[0] ?? host;

const extractHostPattern = (value?: string | null): string | null => {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  // Wildcard host patterns (e.g. *.example.com)
  if (trimmed.includes("*")) {
    return trimmed;
  }

  const tryParse = (candidate: string) => {
    try {
      const parsed = new URL(candidate);
      return parsed.hostname || null;
    } catch {
      return null;
    }
  };

  return (
    tryParse(trimmed) ||
    tryParse(`http://${trimmed}`) ||
    stripPort(trimmed.split("/")[0] ?? "").toLowerCase() ||
    null
  );
};

const allowedDevOriginSet = new Set<string>();

const addOriginPattern = (value?: string | null) => {
  const host = extractHostPattern(value);
  if (host) {
    allowedDevOriginSet.add(host);
  }
};

splitEnvList(process.env.NEXT_PUBLIC_ALLOWED_DEV_ORIGINS).forEach(addOriginPattern);

[
  process.env.NEXT_PUBLIC_APP_URL,
  process.env.NEXT_PUBLIC_FRONTEND_URL,
  process.env.NEXT_PUBLIC_SITE_URL,
  process.env.NEXTAUTH_URL,
  process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : undefined,
].forEach(addOriginPattern);

const privateLanPatterns = [
  "192.168.*.*",
  "10.*.*.*",
  "172.16.*.*",
  "172.17.*.*",
  "172.18.*.*",
  "172.19.*.*",
  "172.20.*.*",
  "172.21.*.*",
  "172.22.*.*",
  "172.23.*.*",
  "172.24.*.*",
  "172.25.*.*",
  "172.26.*.*",
  "172.27.*.*",
  "172.28.*.*",
  "172.29.*.*",
  "172.30.*.*",
  "172.31.*.*",
];

const includePrivateLan =
  process.env.NEXT_ALLOW_PRIVATE_LAN === "true" ||
  (process.env.NEXT_ALLOW_PRIVATE_LAN !== "false" && allowedDevOriginSet.size > 0);

if (includePrivateLan) {
  privateLanPatterns.forEach(pattern => allowedDevOriginSet.add(pattern));
}

const allowedDevOrigins = allowedDevOriginSet.size
  ? Array.from(allowedDevOriginSet)
  : undefined;
const configuredReferrerPolicy =
  process.env.NEXT_REFERRER_POLICY ||
  process.env.NEXT_PUBLIC_REFERRER_POLICY ||
  "strict-origin-when-cross-origin";

const nextConfig: NextConfig = {
  output: 'standalone',
  
  // Disable TypeScript and ESLint errors during build for production
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },

  // Image configuration
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'storage.googleapis.com',
        port: '',
        pathname: '/**',
      },
      {
        protocol: 'https',
        hostname: 'lh3.googleusercontent.com',
        port: '',
        pathname: '/**',
      },
    ],
  },
  
  // Environment variables validation (optional, Next.js loads .env automatically)
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
    NEXT_PUBLIC_FRONTEND_URL: process.env.NEXT_PUBLIC_FRONTEND_URL,
    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY,
    NEXT_PUBLIC_CLERK_SIGN_IN_URL: process.env.NEXT_PUBLIC_CLERK_SIGN_IN_URL,
    NEXT_PUBLIC_CLERK_SIGN_UP_URL: process.env.NEXT_PUBLIC_CLERK_SIGN_UP_URL,
    NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL: process.env.NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL,
    NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL: process.env.NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL,
    NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY: process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY,
  },

  // Required for development when running Next.js server locally and accessing from a different host/port
  allowedDevOrigins,

  // Production optimizations & Experimental features
  experimental: {
    optimizePackageImports: ['@radix-ui/react-icons', 'lucide-react'],
  },

  // Turbopack configuration to explicitly set the workspace root
  turbopack: {
    root: './'
  },

  // Security headers
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'on'
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block'
          },
          {
            key: 'X-Frame-Options',
            value: 'SAMEORIGIN'
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff'
          },
          {
            key: 'Referrer-Policy',
            value: configuredReferrerPolicy
          }
        ]
      }
    ]
  },

  // API Rewrites
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        // Proxy to Backend:
        // 1. Use INTERNAL_API_URL if set (e.g., http://api:8000 in Docker)
        // 2. Fallback to http://localhost:8000 for local development
        destination: `${process.env.INTERNAL_API_URL || 'http://localhost:8000'}/api/:path*`,
      },
    ]
  },

  // Webpack configuration
  webpack: (config, { isServer }) => {
    // Add a rule to handle .glsl files
    config.module.rules.push({
      test: /\.(glsl|vs|fs|vert|frag)$/,
      exclude: /node_modules/,
      use: [
        {
          loader: "raw-loader",
        },
        {
          loader: "glslify-loader",
        },
      ],
    });

    // Fix for react-pdf and webpack compatibility
    config.resolve.alias = {
      ...config.resolve.alias,
      canvas: false,
    };

    // Handle external imports that webpack can't resolve
    if (config.externals) {
      if (Array.isArray(config.externals)) {
        config.externals.push({
          canvas: 'canvas'
        });
      } else {
         // If it's an object or function, we might need to handle differently,
         // but usually pushing to array is safe for Next.js webpack config
         config.externals = [config.externals, { canvas: 'canvas' }];
      }
    } else {
      config.externals = [{
        canvas: 'canvas'
      }];
    }

    // Ignore certain dynamic imports that cause issues
    // Note: 'webpack' is not imported, so we use require
    config.plugins.push(
      new (require('webpack').IgnorePlugin)({
        resourceRegExp: /^\.\/locale$/,
        contextRegExp: /moment$/,
      })
    );

    return config;
  },
};

export default nextConfig;
