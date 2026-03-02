# Frontend On-Premise — Multi-stage build for pnpm monorepo
#
# Build context: frontend/ (monorepo root)
# Usage: docker build -f apps/on-premise/Dockerfile .

# ── Stage 1: Install dependencies and build ──────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@9.0.0 --activate

# Copy workspace config + lockfile first (cache layer)
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/on-premise/package.json ./apps/on-premise/
COPY packages/shared/package.json ./packages/shared/

# Install all dependencies (including shared workspace packages)
RUN pnpm install --frozen-lockfile

# Copy source code
COPY packages/ ./packages/
COPY apps/on-premise/ ./apps/on-premise/

# Build args for NEXT_PUBLIC_* (baked at build time)
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_API_STREAMING_URL
ARG NEXT_PUBLIC_WEAVIATE_SERVICE_URL
ARG NEXT_PUBLIC_EMMA_SERVICE_URL
ARG NEXT_PUBLIC_SSO_AUTHORITY
ARG NEXT_PUBLIC_SSO_CLIENT_ID
ARG NEXT_PUBLIC_SSO_REDIRECT_URI
ARG NEXT_PUBLIC_SSO_POST_LOGOUT_REDIRECT_URI
ARG NEXT_PUBLIC_APP_URL
ARG NEXT_PUBLIC_BACKEND_URL
ARG NEXT_PUBLIC_LANGFUSE_URL

# Limit Node.js heap to avoid OOM during Next.js build
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Build the on-premise app
RUN pnpm --filter @nexus/on-premise build

# ── Stage 2: Production runtime ──────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy standalone output from builder (single React, no broken symlinks)
COPY --from=builder --chown=nextjs:nodejs /app/apps/on-premise/.next/standalone ./
# Copy static assets
COPY --from=builder --chown=nextjs:nodejs /app/apps/on-premise/.next/static ./apps/on-premise/.next/static
# Copy public assets
COPY --from=builder --chown=nextjs:nodejs /app/apps/on-premise/public ./apps/on-premise/public

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:3000/ || exit 1

CMD ["node", "apps/on-premise/server.js"]
