# Frontend — NouxCubeIA

Next.js 15 App Router frontend for the single-tenant document management system.

- **Development guidelines**: see [`../CLAUDE.md`](../CLAUDE.md)
- **Authentication** (KeyCloak OIDC/SAML): see [`../docs/on-premise/AUTHENTICATION.md`](../docs/on-premise/AUTHENTICATION.md)

## Quick start

```bash
nvm use 18  # or 20
npm install
npm run dev  # http://localhost:3001
```

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Dev server on port 3001 (HTTP) |
| `npm run dev:https` | Dev server on port 3001 with experimental HTTPS |
| `npm run build` | Production build |
| `npm run lint` | ESLint |
| `npm run format` | Prettier |
