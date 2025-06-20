# Signature Service Authentication Fix

## Problem
The signature service API calls were failing with 401 Unauthorized errors because the authentication token wasn't being included in the requests.

## Root Cause
The signature service was using the singleton `apiClient` instance which doesn't have authentication configured. The singleton instance doesn't have access to the Clerk authentication context.

## Solution
Created a hook-based version of the signature service that uses the authenticated API client.

### Changes Made:

1. **Created `signature-service.hooks.ts`**
   - A hook version of the signature service that uses `useApiClient()`
   - The `useApiClient()` hook properly configures authentication using Clerk's `getToken()`
   - All service methods are now available through the hook

2. **Updated Components**
   - `signature-request-dialog.tsx` - Now uses `useSignatureService()` hook
   - `signature-request-dialog-v2.tsx` - Now uses `useSignatureService()` hook
   - `provider-config-dialog-v2.tsx` - Now uses `useSignatureService()` hook
   - `provider-config-dialog.tsx` - Now uses `useSignatureService()` hook
   - `delete-provider-dialog.tsx` - Now uses `useSignatureService()` hook
   - `signature-providers/page.tsx` - Now uses `useSignatureService()` hook
   - `documents/page.tsx` - Removed unused import

### Usage Pattern

**Before (Not Authenticated):**
```tsx
import { signatureService } from "@/lib/services/signature-service"

// In component
const providers = await signatureService.getProviders()
```

**After (Authenticated):**
```tsx
import { useSignatureService } from "@/lib/services/signature-service.hooks"

// In component
const signatureService = useSignatureService()
const providers = await signatureService.getProviders()
```

### How It Works

1. The `useApiClient()` hook gets the authentication token from Clerk
2. It creates an API client instance and configures it with the token getter
3. All API requests now include the `Authorization: Bearer <token>` header
4. The backend validates the token and processes the authenticated request

### Benefits

- Proper authentication for all signature service API calls
- Type-safe service methods
- Consistent with other authenticated services in the app
- No changes needed to the backend API

### Testing

To verify the fix:
1. Open the signature providers admin page
2. Check the network tab - requests should now include Authorization headers
3. The providers should load successfully without 401 errors

## Note
The original `signatureService` singleton should only be used in non-component contexts where hooks cannot be used. For all React components, use the `useSignatureService()` hook.