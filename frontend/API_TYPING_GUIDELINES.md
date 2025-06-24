# API Typing Guidelines

## Best Practices for Frontend API Response Typing

### 1. Always Create Specific Types for API Responses

**❌ Bad Practice:**
```typescript
try {
  const response = await apiClient.get('/teams/')
  // response.data is 'any' - no type safety!
  setTeamInfo(response.data)
} catch (error) {
  // error is unknown type
  console.error('Error:', error)
}
```

**✅ Good Practice:**
```typescript
// Define types in a dedicated file
// src/lib/types/teams.ts
export interface TeamInfo {
  id: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
  members_count: number
  storage_quota: number
  is_active: boolean
}

// Use the type in your component
try {
  const response = await apiClient.get<TeamInfo>('/teams/')
  if (!response.error && response.data) {
    setTeamInfo(response.data) // Type-safe!
  }
} catch (error) {
  console.error('Error:', error instanceof Error ? error.message : 'Unknown error')
}
```

### 2. Type Organization Structure

Create type files organized by domain:
```
src/lib/types/
├── teams.ts        # Team-related types
├── documents.ts    # Document-related types
├── users.ts        # User-related types
├── agents.ts       # Agent-related types
└── index.ts        # Re-export common types
```

### 3. Standard Response Types

Create a base response type that all API responses follow:
```typescript
// src/lib/types/api.ts
export interface ApiResponse<T> {
  data?: T
  error?: string
  status: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pages: number
  per_page: number
}
```

### 4. Error Handling with Types

Always handle errors with proper typing:
```typescript
try {
  const response = await apiClient.post<TeamInvitation>('/teams/invitations', data)
  if (!response.error && response.data) {
    // Handle success
  } else {
    throw new Error(response.error || 'Operation failed')
  }
} catch (error) {
  // Type guard for Error instances
  const errorMessage = error instanceof Error 
    ? error.message 
    : 'An unexpected error occurred'
  
  toast({
    title: 'Error',
    description: errorMessage,
    variant: 'destructive'
  })
}
```

### 5. Request Data Types

Also create types for request payloads:
```typescript
export interface CreateTeamRequest {
  name: string
  description?: string
}

export interface UpdateTeamRequest {
  name?: string
  description?: string
}

export interface InviteMemberRequest {
  email: string
  role: 'admin' | 'member'
}
```

### 6. Enum Types for Constants

Use enums or literal types for fixed values:
```typescript
export enum TeamRole {
  ADMIN = 'admin',
  MEMBER = 'member'
}

export enum DocumentStatus {
  PROCESSING = 'PROCESSING',
  INDEXED = 'INDEXED',
  ERROR = 'ERROR'
}

// Or use literal types
export type TeamRole = 'admin' | 'member'
export type DocumentStatus = 'PROCESSING' | 'INDEXED' | 'ERROR'
```

### 7. Date Handling

Always type date fields as strings from API, convert when needed:
```typescript
export interface Document {
  id: string
  created_at: string // ISO 8601 string from API
  updated_at: string
}

// Convert when displaying
const createdDate = new Date(document.created_at)
```

### 8. Optional vs Required Fields

Be explicit about optional fields:
```typescript
export interface User {
  id: string                    // Required
  email: string                 // Required
  full_name: string | null      // Can be null
  phone?: string                // Optional (undefined if not present)
  metadata?: Record<string, any> // Optional object
}
```

### 9. Generic Service Types

Create generic service response types:
```typescript
// Service method that returns typed response
async getTeam(): Promise<ApiResponse<TeamInfo>> {
  return this.apiClient.get<TeamInfo>('/teams/')
}

async getTeamMembers(): Promise<ApiResponse<TeamMember[]>> {
  return this.apiClient.get<TeamMember[]>('/teams/members')
}

async updateTeam(data: UpdateTeamRequest): Promise<ApiResponse<TeamInfo>> {
  return this.apiClient.put<TeamInfo>('/teams/', data)
}
```

### 10. Type Guards for Runtime Validation

Create type guards for critical data:
```typescript
export function isTeamInfo(data: any): data is TeamInfo {
  return (
    typeof data === 'object' &&
    typeof data.id === 'string' &&
    typeof data.name === 'string' &&
    typeof data.members_count === 'number'
  )
}

// Use in component
const response = await apiClient.get('/teams/')
if (!response.error && response.data && isTeamInfo(response.data)) {
  setTeamInfo(response.data)
} else {
  throw new Error('Invalid response format')
}
```

## Benefits

1. **Type Safety**: Catch errors at compile time
2. **IntelliSense**: Better IDE support with autocomplete
3. **Documentation**: Types serve as documentation
4. **Refactoring**: Easier to refactor with confidence
5. **Error Prevention**: Prevents runtime errors from type mismatches

## Example Implementation

See `/src/app/(main)/[tenantId]/admin/teams/page.tsx` for a complete example of proper API typing in practice.