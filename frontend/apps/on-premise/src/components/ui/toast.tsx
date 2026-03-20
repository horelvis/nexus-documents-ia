/**
 * Re-export toast components from shared package
 * This file exists because shared components use @/components/ui/toast
 * which resolves to the app's components directory
 */
export {
  type ToastProps,
  type ToastActionElement,
  ToastProvider,
  ToastViewport,
  Toast,
  ToastTitle,
  ToastDescription,
  ToastClose,
  ToastAction,
} from '@/components/ui'
