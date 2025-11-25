"use client"

import { createContext, useContext, useMemo, useState } from 'react'
import { DemoRequestDialog } from './ui/demo-request-dialog'

type DemoRequestContextValue = {
  open: () => void
  close: () => void
}

const DemoRequestContext = createContext<DemoRequestContextValue | null>(null)

export function DemoRequestProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false)

  const value = useMemo<DemoRequestContextValue>(() => ({
    open: () => setOpen(true),
    close: () => setOpen(false),
  }), [])

  return (
    <DemoRequestContext.Provider value={value}>
      {children}
      <DemoRequestDialog open={open} onOpenChange={setOpen} />
    </DemoRequestContext.Provider>
  )
}

export function useDemoRequest() {
  const ctx = useContext(DemoRequestContext)
  if (!ctx) {
    throw new Error('useDemoRequest must be used within DemoRequestProvider')
  }
  return ctx
}
