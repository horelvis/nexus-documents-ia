# Nexus Document Management - Frontend

## Overview

Nexus Document Management Frontend is a modern, multi-tenant document management system built with Next.js 15, TypeScript, and Tailwind CSS. It provides an intuitive interface for uploading, organizing, and analyzing documents with AI-powered features.

## Tech Stack

- **Framework**: Next.js 15 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS with shadcn/ui components
- **Authentication**: Clerk
- **State Management**: React Context API
- **HTTP Client**: Axios
- **Form Handling**: React Hook Form + Zod validation
- **Icons**: Tabler Icons

## Prerequisites

- Node.js 18.18.0+ or 20.0.0+ (required for Next.js 15)
- npm or yarn package manager
- Backend API running (default: http://localhost:8000)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/your-org/nexus-document-backend.git
cd nexus-document-backend/frontend
```

2. Ensure correct Node version:
```bash
nvm use 18  # or nvm use 20
```

3. Install dependencies:
```bash
npm install
```

4. Create `.env.local` file:
```bash
cp .env.example .env.local
```

5. Configure environment variables:
```env
# Clerk Authentication
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
CLERK_SECRET_KEY=your_clerk_secret_key
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/

# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1

# App Configuration
NEXT_PUBLIC_APP_NAME="Nexus Document Management"
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

## Development

Start the development server:
```bash
npm run dev
```

The application will be available at [http://localhost:3000](http://localhost:3000)

## Project Structure

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── (auth)/            # Authentication pages (sign-in, sign-up)
│   │   ├── (main)/            # Main app layout
│   │   │   └── [tenantId]/    # Tenant-scoped pages
│   │   │       ├── dashboard/
│   │   │       ├── documents/
│   │   │       ├── agents/
│   │   │       └── settings/
│   │   └── layout.tsx         # Root layout
│   ├── components/            # React components
│   │   ├── ui/               # Base UI components (shadcn/ui)
│   │   ├── documents/        # Document-related components
│   │   ├── dashboard/        # Dashboard components
│   │   └── layout/           # Layout components
│   ├── contexts/             # React Context providers
│   ├── hooks/                # Custom React hooks
│   ├── lib/                  # Utilities and services
│   │   ├── services/         # API service layer
│   │   ├── api-client.ts     # Axios configuration
│   │   └── utils.ts          # Helper functions
│   └── styles/               # Global styles
└── public/                   # Static assets
```

## Key Features

### Document Management
- **Upload**: Drag-and-drop or click to upload multiple files
- **Organization**: Categorize documents with tags and custom metadata
- **Views**: Toggle between grid and table views
- **Search**: Full-text search with filters
- **Preview**: In-app document preview with thumbnails
- **Sharing**: Generate secure shareable links

### AI-Powered Features
- **Smart Analysis**: Automatic document analysis and categorization
- **Content Extraction**: Extract text and metadata from various file types
- **AI Agents**: Interactive agents for document Q&A
- **Summaries**: Generate AI-powered document summaries

### User Interface
- **Dark Mode**: Full dark mode support with system preference detection
- **Responsive Design**: Mobile-first responsive design
- **Accessibility**: WCAG compliant components
- **Real-time Updates**: Live notifications for document processing
- **User Preferences**: Persistent UI preferences per tenant

### Multi-Tenant Architecture
- **Tenant Isolation**: Complete data isolation between tenants
- **Custom Branding**: Per-tenant customization options
- **Role-Based Access**: Fine-grained permissions system

## API Integration

The frontend communicates with the backend through a service layer:

```typescript
// Example: Document Service
import { useDocumentService } from '@/lib/services/document.service'

const documentService = useDocumentService()

// Get documents
const response = await documentService.getDocuments({
  search: 'contract',
  status: 'INDEXED',
  page: 1,
  per_page: 20
})

// Upload document
const uploadResponse = await documentService.uploadDocument(file, {
  title: 'My Document',
  tags: ['important', 'contract']
})
```

## Building for Production

1. Build the application:
```bash
npm run build
```

2. Start production server:
```bash
npm start
```

## Testing

Run the test suite:
```bash
npm test
```

Run tests in watch mode:
```bash
npm run test:watch
```

## Code Quality

### Linting
```bash
npm run lint
```

### Type Checking
```bash
npm run type-check
```

### Format Code
```bash
npm run format
```

## Deployment

### Vercel (Recommended)
1. Push to GitHub
2. Import project in Vercel
3. Configure environment variables
4. Deploy

### Docker
```dockerfile
FROM node:18-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:18-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:18-alpine AS runner
WORKDIR /app
ENV NODE_ENV production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
ENV PORT 3000
CMD ["node", "server.js"]
```

## Troubleshooting

### Common Issues

1. **Module Resolution Errors**
   ```bash
   rm -rf .next node_modules
   npm install
   npm run dev
   ```

2. **Node Version Issues**
   ```bash
   nvm use 18
   # or
   nvm install 18
   nvm use 18
   ```

3. **Environment Variables Not Loading**
   - Ensure `.env.local` exists
   - Restart the development server
   - Variables must start with `NEXT_PUBLIC_` to be accessible client-side

4. **Clerk Authentication Issues**
   - Verify Clerk keys are correct
   - Check Clerk dashboard for proper configuration
   - Ensure redirect URLs match your domain

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is proprietary and confidential.

## Support

For support, email support@nexusdocuments.com or join our Slack channel.