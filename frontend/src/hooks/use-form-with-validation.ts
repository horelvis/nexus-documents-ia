import { useState, useCallback, useEffect } from "react"
import { useForm, UseFormProps, UseFormReturn, FieldValues } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useNotifications } from "@/contexts/notifications-context"

interface UseFormWithValidationOptions<TFieldValues extends FieldValues = FieldValues> 
  extends Omit<UseFormProps<TFieldValues>, 'resolver'> {
  schema: z.ZodType<TFieldValues>
  onSubmit: (data: TFieldValues) => Promise<void> | void
  onError?: (error: any) => void
  successMessage?: string
  errorMessage?: string
  resetOnSuccess?: boolean
  validateOnMount?: boolean
  debugMode?: boolean
}

interface UseFormWithValidationReturn<TFieldValues extends FieldValues = FieldValues> 
  extends UseFormReturn<TFieldValues> {
  isSubmitting: boolean
  submitCount: number
  onSubmit: (e?: React.BaseSyntheticEvent) => Promise<void>
  hasErrors: boolean
  errorCount: number
  isDirty: boolean
  resetForm: () => void
  validateField: (fieldName: keyof TFieldValues) => Promise<boolean>
  clearFieldError: (fieldName: keyof TFieldValues) => void
}

export function useFormWithValidation<TFieldValues extends FieldValues = FieldValues>({
  schema,
  onSubmit,
  onError,
  successMessage,
  errorMessage = "An error occurred",
  resetOnSuccess = false,
  validateOnMount = false,
  debugMode = false,
  ...formOptions
}: UseFormWithValidationOptions<TFieldValues>): UseFormWithValidationReturn<TFieldValues> {
  const { addNotification } = useNotifications()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitCount, setSubmitCount] = useState(0)

  // Initialize React Hook Form with Zod resolver
  const form = useForm<TFieldValues>({
    ...formOptions,
    resolver: zodResolver(schema),
  })

  const {
    handleSubmit,
    formState: { errors, isDirty },
    reset,
    trigger,
    clearErrors,
    setError,
  } = form

  // Debug mode logging
  useEffect(() => {
    if (debugMode) {
      console.log("Form State:", {
        values: form.getValues(),
        errors: errors,
        isDirty: isDirty,
        isSubmitting: isSubmitting,
        submitCount: submitCount,
      })
    }
  }, [form.watch(), errors, isDirty, isSubmitting, submitCount, debugMode])

  // Validate on mount if requested
  useEffect(() => {
    if (validateOnMount) {
      trigger()
    }
  }, [validateOnMount, trigger])

  // Calculate error state
  const hasErrors = Object.keys(errors).length > 0
  const errorCount = Object.keys(errors).length

  // Handle form submission
  const handleFormSubmit = useCallback(
    async (data: TFieldValues) => {
      setIsSubmitting(true)
      setSubmitCount(prev => prev + 1)

      try {
        await onSubmit(data)

        if (successMessage) {
          addNotification({
            type: 'success',
            title: 'Success',
            message: successMessage,
          })
        }

        if (resetOnSuccess) {
          reset()
        }
      } catch (error: any) {
        console.error("Form submission error:", error)

        // Handle validation errors from the server
        if (error.response?.data?.errors) {
          Object.entries(error.response.data.errors).forEach(([field, message]) => {
            setError(field as any, {
              type: 'server',
              message: message as string,
            })
          })
        }

        // Call custom error handler if provided
        if (onError) {
          onError(error)
        } else {
          // Default error handling
          addNotification({
            type: 'error',
            title: 'Error',
            message: error.message || errorMessage,
          })
        }
      } finally {
        setIsSubmitting(false)
      }
    },
    [onSubmit, onError, successMessage, errorMessage, resetOnSuccess, reset, setError, addNotification]
  )

  // Reset form helper
  const resetForm = useCallback(() => {
    reset()
    setSubmitCount(0)
  }, [reset])

  // Validate specific field
  const validateField = useCallback(
    async (fieldName: keyof TFieldValues): Promise<boolean> => {
      const result = await trigger(fieldName as any)
      return result
    },
    [trigger]
  )

  // Clear specific field error
  const clearFieldError = useCallback(
    (fieldName: keyof TFieldValues) => {
      clearErrors(fieldName as any)
    },
    [clearErrors]
  )

  // Create submit handler
  const onSubmitHandler = handleSubmit(handleFormSubmit)

  return {
    ...form,
    isSubmitting,
    submitCount,
    onSubmit: onSubmitHandler,
    hasErrors,
    errorCount,
    isDirty,
    resetForm,
    validateField,
    clearFieldError,
  }
}

// Helper hook for field arrays with validation
export function useFieldArrayWithValidation<TFieldValues extends FieldValues = FieldValues>(
  form: UseFormReturn<TFieldValues>,
  name: any,
  options?: {
    minItems?: number
    maxItems?: number
    onAdd?: () => void
    onRemove?: (index: number) => void
  }
) {
  const { addNotification } = useNotifications()
  const fieldArray = form.control._fields[name] || []

  const canAdd = !options?.maxItems || fieldArray.length < options.maxItems
  const canRemove = !options?.minItems || fieldArray.length > options.minItems

  const handleAdd = useCallback(() => {
    if (!canAdd) {
      addNotification({
        type: 'error',
        title: 'Limit reached',
        message: `Maximum ${options?.maxItems} items allowed`,
      })
      return false
    }
    options?.onAdd?.()
    return true
  }, [canAdd, options, addNotification])

  const handleRemove = useCallback((index: number) => {
    if (!canRemove) {
      addNotification({
        type: 'error',
        title: 'Minimum required',
        message: `At least ${options?.minItems} items required`,
      })
      return false
    }
    options?.onRemove?.(index)
    return true
  }, [canRemove, options, addNotification])

  return {
    canAdd,
    canRemove,
    handleAdd,
    handleRemove,
  }
}