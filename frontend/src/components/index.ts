/**
 * Main Component Exports
 * Organized by feature/functionality for better tree-shaking and maintainability
 */

// Authentication Components - Login/logout and auth guards
export * from './auth';

// Landing Page Components - Homepage sections
export * from './landing';

// Layout Components - Main app structure
export * from './layout';

// Navigation Components - Menu and navigation elements
export * from './navigation';

// Dashboard Components - Dashboard-specific features
export * from './dashboard';

// Common Reusable Components - Shared across app
export * from './common';

// Provider Components - Context and state providers
export * from './providers';

// UI Components - Base design system (shadcn/ui)
export * from './ui';

// Type exports for better TypeScript support
// Note: Import React types individually to avoid module resolution issues