/**
 * Type stub for @/lib/services/emma.service.
 * Actual implementation lives in the consuming app.
 */
export interface EmmaStreamEvent {
  event: string
  data: Record<string, any>
}

export interface EmmaError {
  type: string
  message: string
  titleKey: string
  messageKey: string
  canRetry: boolean
  retryable?: boolean
  statusCode?: number
  originalError?: Error
}

export declare function classifyError(error: unknown): EmmaError

export declare function useEmmaService(): {
  queryEmma: (...args: any[]) => Promise<any>
  queryEmmaStream: (...args: any[]) => Promise<any>
  queryEmmaStreamGenerator: (...args: any[]) => AsyncGenerator<EmmaStreamEvent>
  resumeQueryStreamGenerator: (...args: any[]) => AsyncGenerator<EmmaStreamEvent>
  uploadTempDocument: (...args: any[]) => Promise<any>
  getAvailableAgents: (...args: any[]) => Promise<any>
  sendMessage: (...args: any[]) => Promise<any>
  getWelcomeMessage: (...args: any[]) => Promise<any>
}
