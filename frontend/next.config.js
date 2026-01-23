/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  allowedDevOrigins: ['http://nouxcube.local:3001', '192.168.1.58'],
  eslint: {
    // Warning: This allows production builds to successfully complete even if
    // your project has ESLint errors.
    ignoreDuringBuilds: true,
  },
  typescript: {
    // Warning: This allows production builds to successfully complete even if
    // your project has type errors.
    ignoreBuildErrors: true,
  },
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
  async headers() {
    return [
      {
        // Serve .mjs files with correct MIME type for PDF.js worker
        source: '/:path*.mjs',
        headers: [
          {
            key: 'Content-Type',
            value: 'application/javascript'
          }
        ]
      },
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
            value: 'strict-origin-when-cross-origin'
          }
        ]
      }
    ]
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        // IMPORTANT:
        // - `destination` must be an absolute URL (server-side rewrite).
        // - Do NOT use `NEXT_PUBLIC_*` here: those may be set to "/api" (relative), which would break rewrites.
        // - Configure `API_BASE_URL` (server-only) in the frontend runtime.
        destination: `${process.env.API_BASE_URL || 'http://127.0.0.1:8000'}/api/:path*`,
      },
    ]
  },
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
      config.externals.push({
        canvas: 'canvas'
      });
    } else {
      config.externals = [{
        canvas: 'canvas'
      }];
    }

    // Ignore certain dynamic imports that cause issues
    config.plugins.push(
      new (require('webpack').IgnorePlugin)({
        resourceRegExp: /^\.\/locale$/,
        contextRegExp: /moment$/,
      })
    );

    return config;
  },
}

module.exports = nextConfig
