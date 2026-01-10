# Nexus Document Management - Frontend

## Overview

Nexus Document Management Frontend is a cutting-edge, multi-tenant intelligent document management system built with Next.js 15, TypeScript, and modern React patterns. It provides a sophisticated yet intuitive interface for uploading, organizing, analyzing, and managing documents with powerful AI-driven capabilities.

## Key Features

### Modern Architecture
- **Next.js 15 with App Router**: Leverages the latest Next.js features including server components, streaming, and improved performance
- **TypeScript Strict Mode**: Full type safety with strict TypeScript configuration for enhanced code quality
- **Multi-Tenant Support**: Complete tenant isolation with organization-based data segregation
- **Real-time Updates**: WebSocket integration for live document processing notifications

### Enhanced User Interface
- **Collapsible Sidebar Navigation**: Advanced sidebar with smooth animations, submenus, and persistent state
- **Responsive Design**: Mobile-first approach with adaptive layouts for all screen sizes
- **Dark Mode Support**: System-aware theme switching with persistent user preferences
- **Enhanced 404 Page**: Custom error pages with engaging animations and helpful navigation
- **Loading States**: Consistent loading patterns with skeleton screens and progress indicators

### Document Management
- **Smart Upload**: Drag-and-drop or click-to-upload with multi-file support and progress tracking
- **Advanced Organization**: Hierarchical categorization with tags, folders, and custom metadata
- **Multiple View Modes**: Toggle between grid, table, and list views with persistent preferences
- **Powerful Search**: Full-text search with advanced filters, facets, and real-time suggestions
- **Document Preview**: In-app preview with thumbnail generation and full-screen mode
- **Secure Sharing**: Generate time-limited, password-protected shareable links
- **Bulk Operations**: Select and perform actions on multiple documents simultaneously
- **Version Control**: Track document versions with diff viewing and rollback capabilities

### AI-Powered Features
- **Intelligent Analysis**: Automatic document classification and content extraction
- **Smart Summaries**: AI-generated document summaries with key points extraction
- **Interactive AI Agents**: Chat with documents using context-aware AI assistants
- **Content Recognition**: OCR support for scanned documents and images
- **Semantic Search**: Find documents based on meaning, not just keywords
- **Auto-tagging**: Intelligent tag suggestions based on document content

### Security & Authentication
- **Clerk Integration**: Enterprise-grade authentication with SSO support
- **Role-Based Access Control**: Fine-grained permissions at document and feature level
- **Audit Trails**: Comprehensive logging of all document activities
- **Data Encryption**: End-to-end encryption for sensitive documents

## Tech Stack

- **Framework**: Next.js 15.1.4 with App Router and Turbopack
- **Language**: TypeScript 5.7.3 with strict mode enabled
- **Styling**: Tailwind CSS 3.4.17 with custom design system
- **Component Library**: shadcn/ui with Radix UI primitives
- **Authentication**: Clerk 6.8.0 with multi-tenant support
- **State Management**: React Context API with custom hooks
- **HTTP Client**: Axios with interceptors for auth and error handling
- **Form Handling**: React Hook Form 7.54.2 + Zod 3.24.1 validation
- **Icons**: Tabler Icons with custom icon components
- **Charts**: Recharts for data visualization
- **Date Handling**: date-fns for consistent date formatting
- **File Upload**: react-dropzone with progress tracking

## Prerequisites

- Node.js 18.18.0+ or 20.0.0+ (required for Next.js 15)
- npm 9+ or yarn 1.22+
- Backend API running (default: http://localhost:8000)
- Clerk account for authentication
- Modern browser with ES6+ support

## Installation

1. Clone the repository:
```bash
git clone https://github.com/your-org/nexus-document-backend.git
cd nexus-document-backend/frontend
```

2. Ensure correct Node version:
```bash
# Check current version
node --version

# Use NVM to switch versions if needed
nvm use 18  # or nvm use 20
```

3. Install dependencies:
```bash
npm install
```

4. Create environment configuration:
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
# Recommended (proxy through Next.js): keep browser calls on same-origin `/api/*`
API_BASE_URL=http://localhost:8000

# Optional (direct-from-browser calls): set an absolute backend base URL
# NEXT_PUBLIC_API_URL=http://localhost:8000

# App Configuration
NEXT_PUBLIC_APP_NAME="Nexus Document Management"
NEXT_PUBLIC_APP_URL=http://localhost:3000

# Feature Flags
NEXT_PUBLIC_ENABLE_AI_FEATURES=true
NEXT_PUBLIC_ENABLE_NOTIFICATIONS=true
```

## Development

### Start Development Server
```bash
npm run dev
```

The application will be available at [http://localhost:3000](http://localhost:3000)

### Development Commands
```bash
# Start with Turbopack (faster HMR)
npm run dev

# Build for production
npm run build

# Start production server
npm start

# Run linting
npm run lint

# Type checking
npm run type-check

# Format code
npm run format

# Run tests
npm test

# Run tests in watch mode
npm run test:watch
```

## Project Structure

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── (auth)/            # Authentication pages layout
│   │   │   ├── sign-in/       # Sign in page
│   │   │   └── sign-up/       # Sign up page
│   │   ├── (main)/            # Main app layout with sidebar
│   │   │   └── [tenantId]/    # Tenant-scoped pages
│   │   │       ├── dashboard/ # Dashboard with analytics
│   │   │       ├── documents/ # Document management
│   │   │       ├── agents/    # AI agent interactions
│   │   │       ├── settings/  # User and app settings
│   │   │       └── shared/    # Shared documents
│   │   ├── api/               # API route handlers
│   │   ├── error.tsx          # Error boundary
│   │   ├── not-found.tsx      # Enhanced 404 page
│   │   └── layout.tsx         # Root layout with providers
│   ├── components/            # React components
│   │   ├── ui/               # Base UI components (shadcn/ui)
│   │   │   ├── button.tsx    # Button variations
│   │   │   ├── dialog.tsx    # Modal dialogs
│   │   │   ├── card.tsx      # Card components
│   │   │   └── ...           # Other UI primitives
│   │   ├── documents/        # Document-specific components
│   │   │   ├── document-upload.tsx
│   │   │   ├── document-list.tsx
│   │   │   └── document-preview.tsx
│   │   ├── dashboard/        # Dashboard components
│   │   │   ├── stats-card.tsx
│   │   │   ├── recent-activity.tsx
│   │   │   └── usage-chart.tsx
│   │   ├── layout/           # Layout components
│   │   │   ├── sidebar.tsx   # Collapsible sidebar
│   │   │   ├── header.tsx    # Top navigation
│   │   │   └── footer.tsx    # Footer component
│   │   └── shared/           # Shared components
│   │       ├── loader.tsx    # Loading indicators
│   │       ├── error-boundary.tsx
│   │       └── empty-state.tsx
│   ├── contexts/             # React Context providers
│   │   ├── tenant-context.tsx # Multi-tenant context
│   │   ├── ui-context.tsx     # UI preferences
│   │   └── notification-context.tsx
│   ├── hooks/                # Custom React hooks
│   │   ├── use-tenant.ts     # Tenant management
│   │   ├── use-documents.ts  # Document operations
│   │   └── use-debounce.ts   # Utility hooks
│   ├── lib/                  # Utilities and services
│   │   ├── services/         # API service layer
│   │   │   ├── document.service.ts
│   │   │   ├── agent.service.ts
│   │   │   └── auth.service.ts
│   │   ├── api-client.ts     # Axios configuration
│   │   ├── utils.ts          # Helper functions
│   │   └── constants.ts      # App constants
│   ├── styles/               # Global styles
│   │   └── globals.css       # Tailwind imports
│   └── types/                # TypeScript definitions
│       ├── api.d.ts          # API response types
│       └── global.d.ts       # Global type definitions
└── public/                   # Static assets
    ├── images/              # Image assets
    └── fonts/               # Custom fonts
```

## Architecture Details

### Component Architecture
The application follows a modular component architecture with clear separation of concerns:

- **Pages**: Server components in the App Router handle routing and data fetching
- **Components**: Client components for interactivity, organized by domain
- **Services**: API communication layer with typed interfaces
- **Contexts**: Global state management using React Context
- **Hooks**: Custom hooks for business logic and state management

### State Management
The application uses React Context for global state management, following the Simple UI Pattern:

```typescript
// Simple loading pattern - NO complex hooks
const loadData = async () => {
  setIsLoading(true)
  setError(null)
  
  try {
    const response = await service.getData()
    if (response.error) {
      setError(response.error)
    } else {
      setData(response.data)
    }
  } catch (err) {
    setError(err.message)
  } finally {
    setIsLoading(false)
  }
}
```

### Multi-Tenant Architecture
- **Tenant Isolation**: Each organization has isolated data and settings
- **URL Structure**: `/[tenantId]/feature` for tenant-scoped routes
- **Context Provider**: TenantContext manages current tenant state
- **API Integration**: Tenant ID automatically included in API requests

## UI/UX Patterns

### Simple UI Pattern (MANDATORY)
The application follows a simple, predictable pattern for all data operations:

1. **Show Loader**: Display loading state immediately
2. **Call Backend**: Make API request
3. **Handle Response**: Update UI with data or error
4. **Hide Loader**: Always hide loader in finally block

**What to avoid:**
- Complex useCallback/useMemo for simple operations
- Automatic search/debouncing (use explicit user actions)
- Multiple simultaneous API calls
- Progress simulation with intervals
- Over-engineered state management

### Design System
- **Colors**: Consistent color palette with CSS variables
- **Typography**: System font stack with fallbacks
- **Spacing**: 4px base unit spacing system
- **Components**: Consistent component APIs and behaviors
- **Animations**: Smooth transitions with Framer Motion
- **Responsive**: Mobile-first breakpoints (sm, md, lg, xl, 2xl)

### Accessibility
- **WCAG 2.1 AA Compliant**: All components meet accessibility standards
- **Keyboard Navigation**: Full keyboard support for all interactions
- **Screen Reader Support**: Proper ARIA labels and live regions
- **Focus Management**: Clear focus indicators and logical tab order
- **Color Contrast**: Sufficient contrast ratios for all text

## Development Guidelines

### Code Style
- **TypeScript**: Use strict mode, avoid `any` types
- **Components**: Functional components with TypeScript interfaces
- **Naming**: PascalCase for components, camelCase for functions
- **Imports**: Absolute imports using `@/` prefix
- **Comments**: JSDoc for public APIs, inline comments for complex logic

### Component Guidelines
```typescript
// Example component structure
interface DocumentCardProps {
  document: Document
  onSelect?: (id: string) => void
  className?: string
}

export function DocumentCard({ 
  document, 
  onSelect,
  className 
}: DocumentCardProps) {
  // Simple state management
  const [isLoading, setIsLoading] = useState(false)
  
  // Direct event handlers (no useCallback)
  const handleClick = () => {
    if (onSelect) {
      onSelect(document.id)
    }
  }
  
  return (
    <Card className={cn("cursor-pointer", className)} onClick={handleClick}>
      {/* Component content */}
    </Card>
  )
}
```

### Performance Best Practices
- **Code Splitting**: Dynamic imports for large components
- **Image Optimization**: Use Next.js Image component
- **Bundle Size**: Monitor with webpack-bundle-analyzer
- **Lazy Loading**: Implement for below-fold content
- **Caching**: Leverage browser and CDN caching

## Testing

### Unit Tests
```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage
```

### E2E Tests
```bash
# Run Cypress tests
npm run cypress:open

# Run in headless mode
npm run cypress:run
```

### Testing Guidelines
- Test user interactions, not implementation details
- Use React Testing Library for component tests
- Mock external dependencies (API calls, Clerk)
- Maintain high test coverage (>80%)

## Building for Production

### Production Build
```bash
# Create optimized production build
npm run build

# Analyze bundle size
npm run analyze
```

### Environment-Specific Builds
```bash
# Development build
NODE_ENV=development npm run build

# Staging build
NODE_ENV=staging npm run build

# Production build
NODE_ENV=production npm run build
```

## Deployment

### Vercel (Recommended)
1. Connect GitHub repository
2. Configure environment variables
3. Set Node.js version to 18.x or 20.x
4. Deploy with automatic previews

### Docker
```dockerfile
# Multi-stage build for optimized image
FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
ENV PORT 3000
CMD ["node", "server.js"]
```

### Environment Configuration
Ensure all required environment variables are set in production:
- Use secrets management for sensitive values
- Set appropriate CORS origins
- Configure CDN for static assets
- Enable security headers

## Troubleshooting

### Common Issues

1. **Module Resolution Errors**
   ```bash
   # Clear Next.js cache and reinstall
   rm -rf .next node_modules
   npm install
   npm run dev
   ```

2. **Node Version Issues**
   ```bash
   # Check current version
   node --version
   
   # Switch using NVM
   nvm use 20
   nvm alias default 20
   ```

3. **TypeScript Errors**
   ```bash
   # Check for type errors
   npm run type-check
   
   # Update TypeScript
   npm update typescript @types/react @types/node
   ```

4. **Build Failures**
   ```bash
   # Clean build
   rm -rf .next
   npm run build
   
   # Check for missing dependencies
   npm ls
   ```

5. **Clerk Authentication Issues**
   - Verify publishable key is correct
   - Check allowed origins in Clerk dashboard
   - Ensure redirect URLs match environment
   - Clear browser cookies/localStorage

6. **API Connection Issues**
   - Verify NEXT_PUBLIC_API_URL is correct
   - Check CORS configuration on backend
   - Ensure backend is running and accessible
   - Check network tab for detailed errors

7. **Tailwind CSS Not Working**
   - Ensure Tailwind config includes all content paths
   - Check for PostCSS configuration
   - Restart dev server after config changes
   - Verify globals.css imports Tailwind directives

8. **State Management Issues**
   - Check Context Provider wrapping
   - Verify hooks are used within providers
   - Look for missing dependencies in useEffect
   - Ensure proper cleanup in useEffect returns

### Performance Troubleshooting

1. **Slow Initial Load**
   - Check bundle size with analyzer
   - Implement code splitting
   - Optimize images and fonts
   - Enable Next.js automatic static optimization

2. **Memory Leaks**
   - Check for missing useEffect cleanups
   - Remove event listeners properly
   - Cancel pending API requests
   - Use React DevTools Profiler

3. **Slow Re-renders**
   - Avoid unnecessary state updates
   - Use React.memo for expensive components
   - Check for large lists without virtualization
   - Profile with React DevTools

## Advanced Configuration

### Custom Webpack Configuration
```javascript
// next.config.js
module.exports = {
  webpack: (config, { isServer }) => {
    // Custom webpack modifications
    return config
  }
}
```

### Custom Server
```javascript
// server.js
const { createServer } = require('http')
const { parse } = require('url')
const next = require('next')

const dev = process.env.NODE_ENV !== 'production'
const app = next({ dev })
const handle = app.getRequestHandler()

app.prepare().then(() => {
  createServer((req, res) => {
    handle(req, res, parse(req.url, true))
  }).listen(3000)
})
```

## Contributing

### Development Workflow
1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Make changes following guidelines
4. Write/update tests
5. Commit with conventional commits: `git commit -m 'feat: add amazing feature'`
6. Push to branch: `git push origin feature/amazing-feature`
7. Open Pull Request with detailed description

### Code Review Checklist
- [ ] TypeScript types are properly defined
- [ ] Components follow Simple UI Pattern
- [ ] No unnecessary complex hooks
- [ ] Tests are included and passing
- [ ] Documentation is updated
- [ ] Accessibility standards are met
- [ ] Performance impact is considered

### Commit Convention
- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc)
- `refactor:` Code refactoring
- `test:` Test additions or changes
- `chore:` Build process or auxiliary tool changes

## Security

### Best Practices
- Never commit sensitive data or credentials
- Use environment variables for configuration
- Implement proper input validation
- Sanitize user-generated content
- Keep dependencies updated
- Use HTTPS in production
- Implement rate limiting
- Add security headers

### Security Headers
```javascript
// next.config.js
module.exports = {
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY'
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff'
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block'
          }
        ]
      }
    ]
  }
}
```

## License

This project is proprietary and confidential. All rights reserved.

## Support

For support and questions:
- Email: support@nexusdocuments.com
- Documentation: https://docs.nexusdocuments.com
- Slack: Join our community workspace
- Issues: GitHub Issues for bug reports

---

Built with ❤️ by the Nexus Team
