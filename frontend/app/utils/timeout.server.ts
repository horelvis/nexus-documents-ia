// frontend/app/utils/timeout.server.ts - IMPLEMENTACIÓN PROPIA
export class TimeoutError extends Error {
    constructor(message: string) {
      super(message)
      this.name = 'TimeoutError'
    }
  }
  
  /**
   * Implementación propia de timeout que SÍ funciona en Remix
   * Basada en remix-utils pero sin dependencias externas
   */
  export async function timeout<T>(
    promise: Promise<T>,
    options: {
      ms: number
      signal?: AbortSignal
    }
  ): Promise<T> {
    const { ms, signal } = options
  
    // Si ya está abortado, rechazar inmediatamente
    if (signal?.aborted) {
      throw new Error('Operation aborted')
    }
  
    return new Promise<T>((resolve, reject) => {
      let timeoutId: NodeJS.Timeout
      let signalHandler: (() => void) | undefined
  
      // Configurar timeout
      timeoutId = setTimeout(() => {
        cleanup()
        reject(new TimeoutError(`Operation timed out after ${ms}ms`))
      }, ms)
  
      // Configurar AbortSignal si está presente
      if (signal) {
        signalHandler = () => {
          cleanup()
          reject(new Error('Operation aborted'))
        }
        signal.addEventListener('abort', signalHandler, { once: true })
      }
  
      // Función de limpieza
      const cleanup = () => {
        clearTimeout(timeoutId)
        if (signal && signalHandler) {
          signal.removeEventListener('abort', signalHandler)
        }
      }
  
      // Manejar la promesa original
      promise
        .then((result) => {
          cleanup()
          resolve(result)
        })
        .catch((error) => {
          cleanup()
          reject(error)
        })
    })
  }