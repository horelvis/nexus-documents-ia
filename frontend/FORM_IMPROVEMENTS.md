# Form Improvements with Zod and React Hook Form

This document outlines the improvements made to forms using Zod for schema validation and React Hook Form for form management.

## Overview

We've created improved versions of the forms with the following benefits:
- **Type-safe validation** using Zod schemas
- **Better form state management** with React Hook Form
- **Consistent error handling** across all forms
- **Improved UX** with real-time validation and better error messages
- **Reusable patterns** for common validation scenarios

## Improved Forms

### 1. Signature Request Dialog (`signature-request-dialog-v2.tsx`)

**Schema**: `/lib/schemas/signature-request.ts`

**Key Improvements**:
- Dynamic signer fields with proper validation
- Email validation for each signer
- Controlled expiration date with slider
- Better error messages for each field
- Form-level validation before submission

**Usage Example**:
```tsx
import { SignatureRequestDialogV2 } from "@/components/documents/signature-request-dialog-v2"

// In your component
<SignatureRequestDialogV2
  document={selectedDocument}
  open={isOpen}
  onOpenChange={setIsOpen}
/>
```

### 2. Provider Configuration Dialog (`provider-config-dialog-v2.tsx`)

**Schema**: `/lib/schemas/signature-provider.ts`

**Key Improvements**:
- Discriminated union for different provider types
- Dynamic credential fields based on provider
- Real-time connection testing with validation
- Visual provider selection
- Secure credential handling

**Usage Example**:
```tsx
import { ProviderConfigDialogV2 } from "@/components/admin/provider-config-dialog-v2"

// In your component
<ProviderConfigDialogV2
  open={isOpen}
  onOpenChange={setIsOpen}
  provider={existingProvider} // Optional for editing
  onSuccess={handleSuccess}
/>
```

### 3. Share Document Dialog (Schema Ready)

**Schema**: `/lib/schemas/share-document.ts`

**Features**:
- Discriminated union for email/link sharing
- Password strength validation
- Permission management
- Expiration and access limit validation

### 4. Edit Document Dialog (Schema Ready)

**Schema**: `/lib/schemas/edit-document.ts`

**Features**:
- Tag validation and formatting
- Category selection with icons
- Metadata management
- Auto-trimming of text fields

## Key Patterns and Utilities

### 1. Custom Form Hook

**File**: `/hooks/use-form-with-validation.ts`

Provides a wrapper around React Hook Form with common patterns:
```tsx
const form = useFormWithValidation({
  schema: mySchema,
  onSubmit: async (data) => {
    // Handle submission
  },
  successMessage: "Form submitted successfully",
  resetOnSuccess: true,
})
```

### 2. Common Validation Utilities

**File**: `/lib/utils/form-validation.ts`

Reusable validation patterns:
- Email, phone, URL validation
- Password strength requirements
- File type and size validation
- Sanitization helpers

### 3. Form Components Integration

All improved forms use the shadcn/ui Form components for consistent styling:
```tsx
<Form {...form}>
  <form onSubmit={form.handleSubmit(onSubmit)}>
    <FormField
      control={form.control}
      name="fieldName"
      render={({ field }) => (
        <FormItem>
          <FormLabel>Field Label</FormLabel>
          <FormControl>
            <Input {...field} />
          </FormControl>
          <FormDescription>
            Helper text
          </FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  </form>
</Form>
```

## Migration Guide

To migrate existing forms to use the new pattern:

1. **Create a Zod Schema**:
```tsx
const schema = z.object({
  field1: z.string().min(1, "Required"),
  field2: z.number().positive(),
})
```

2. **Replace useState with useForm**:
```tsx
// Before
const [field1, setField1] = useState("")
const [field2, setField2] = useState(0)

// After
const form = useForm({
  resolver: zodResolver(schema),
  defaultValues: {
    field1: "",
    field2: 0,
  }
})
```

3. **Update Form JSX**:
```tsx
// Before
<Input 
  value={field1} 
  onChange={(e) => setField1(e.target.value)} 
/>

// After
<FormField
  control={form.control}
  name="field1"
  render={({ field }) => (
    <FormItem>
      <FormControl>
        <Input {...field} />
      </FormControl>
      <FormMessage />
    </FormItem>
  )}
/>
```

4. **Replace Manual Validation**:
```tsx
// Before
const validateForm = () => {
  if (!field1) {
    showError("Field 1 is required")
    return false
  }
  return true
}

// After
// Validation happens automatically with Zod schema
const onSubmit = async (data) => {
  // Data is already validated
}
```

## Best Practices

1. **Define Schemas in Separate Files**: Keep schemas in `/lib/schemas/` for reusability
2. **Use Discriminated Unions**: For forms with conditional fields based on a type
3. **Leverage Transform Functions**: For data normalization (trim, lowercase, etc.)
4. **Provide Clear Error Messages**: Use descriptive validation messages in schemas
5. **Test Edge Cases**: Ensure validation covers all scenarios
6. **Use Type Inference**: Let TypeScript infer types from schemas

## Benefits

1. **Type Safety**: Full TypeScript support with inferred types
2. **Better UX**: Real-time validation with clear error messages
3. **Reduced Boilerplate**: Less code for form state management
4. **Consistency**: Uniform validation patterns across the app
5. **Maintainability**: Centralized schemas make updates easier
6. **Performance**: Optimized re-renders with React Hook Form

## Next Steps

To use these improved forms in your application:

1. Import the v2 components instead of the original ones
2. Update any parent components to use the new props
3. Remove old validation logic
4. Test thoroughly with various inputs

The improved forms provide a much better developer experience and user experience while maintaining all the original functionality.