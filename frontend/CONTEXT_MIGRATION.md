# Context Migration Guide

## Overview
We've simplified the context structure by combining NotificationsContext and ConnectionContext into a unified AppStateContext.

## Migration Steps

### 1. Update Imports

#### Before:
```typescript
import { useNotifications } from '@/contexts/notifications-context'
import { useConnection } from '@/contexts/connection-context'
```

#### After:
```typescript
import { useNotifications, useConnection } from '@/contexts/app-state-context'
// or use the main hook:
import { useAppState } from '@/contexts/app-state-context'
```

### 2. Provider Changes

The providers are now automatically included in the main layout via `AppProviders`, so you don't need to wrap components with individual providers anymore.

#### Before:
```typescript
<NotificationsProvider>
  <UploadProvider>
    <ConnectionProvider>
      {children}
    </ConnectionProvider>
  </UploadProvider>
</NotificationsProvider>
```

#### After:
```typescript
// Providers are already included in the root layout
{children}
```

### 3. Available Hooks

#### From app-state-context.tsx:
- `useAppState()` - Access all app state (connection + notifications)
- `useNotifications()` - Same API as before
- `useConnection()` - Same API as before

#### Still separate:
- `useUpload()` - From upload-context.tsx
- `useUserContext()` - From user-context.tsx
- `useBackendUser()` - From user-context.tsx
- `useOnboardingStatus()` - From user-context.tsx

## Benefits

1. **Reduced Provider Nesting**: Less wrapper components in layouts
2. **Unified State Management**: Connection and notifications are related and now managed together
3. **Automatic Connection Notifications**: The system now automatically shows notifications when connection is restored
4. **Simpler Imports**: Import related functionality from one place

## Files to Update

Run these commands to find files that need updating:
```bash
# Find files using old notification context
grep -r "notifications-context" --include="*.tsx" --include="*.ts"

# Find files using old connection context  
grep -r "connection-context" --include="*.tsx" --include="*.ts"
```