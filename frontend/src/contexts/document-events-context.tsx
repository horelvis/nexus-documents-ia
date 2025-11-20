"use client"

import { ReactNode, createContext, useContext, useMemo, useRef, useEffect } from "react"

type UploadResult = {
  id: string
  status: string
  file?: File
}

type DocumentEventPayloads = {
  "documents:updated": {
    tenantId?: string
    source?: "upload" | "delete" | "edit" | "refresh"
    files?: UploadResult[]
  }
}

export type DocumentsUpdatedPayload = DocumentEventPayloads["documents:updated"]

type DocumentEventName = keyof DocumentEventPayloads
type DocumentEventHandler<T extends DocumentEventName> = (payload?: DocumentEventPayloads[T]) => void

interface DocumentEventsContextValue {
  emitDocumentEvent: <T extends DocumentEventName>(event: T, payload?: DocumentEventPayloads[T]) => void
  subscribeToDocumentEvent: <T extends DocumentEventName>(event: T, handler: DocumentEventHandler<T>) => () => void
}

const DocumentEventsContext = createContext<DocumentEventsContextValue | null>(null)

type DocumentEventsStore = {
  emit: DocumentEventsContextValue["emitDocumentEvent"]
  subscribe: DocumentEventsContextValue["subscribeToDocumentEvent"]
}

function createDocumentEventsStore(): DocumentEventsStore {
  const listeners = new Map<DocumentEventName, Set<DocumentEventHandler<DocumentEventName>>>()

  return {
    emit: (event, payload) => {
      const handlers = listeners.get(event)
      if (!handlers || handlers.size === 0) {
        return
      }

      handlers.forEach((handler) => {
        try {
          handler(payload)
        } catch (error) {
          console.error(`[DocumentEvents] Handler for "${event}" failed`, error)
        }
      })
    },
    subscribe: (event, handler) => {
      const handlers = listeners.get(event) ?? new Set()
      handlers.add(handler as DocumentEventHandler<DocumentEventName>)
      listeners.set(event, handlers)

      return () => {
        const currentHandlers = listeners.get(event)
        if (!currentHandlers) {
          return
        }

        currentHandlers.delete(handler as DocumentEventHandler<DocumentEventName>)
        if (currentHandlers.size === 0) {
          listeners.delete(event)
        }
      }
    }
  }
}

export function DocumentEventsProvider({ children }: { children: ReactNode }) {
  const storeRef = useRef<DocumentEventsStore>()

  if (!storeRef.current) {
    storeRef.current = createDocumentEventsStore()
  }

  const value = useMemo<DocumentEventsContextValue>(() => ({
    emitDocumentEvent: storeRef.current!.emit,
    subscribeToDocumentEvent: storeRef.current!.subscribe
  }), [])

  return (
    <DocumentEventsContext.Provider value={value}>
      {children}
    </DocumentEventsContext.Provider>
  )
}

export function useDocumentEvents() {
  const context = useContext(DocumentEventsContext)
  if (!context) {
    throw new Error("useDocumentEvents must be used within a DocumentEventsProvider")
  }
  return context
}

export function useDocumentEvent<T extends DocumentEventName>(
  event: T,
  handler: DocumentEventHandler<T>
) {
  const { subscribeToDocumentEvent } = useDocumentEvents()

  useEffect(() => {
    return subscribeToDocumentEvent(event, handler)
  }, [event, handler, subscribeToDocumentEvent])
}
