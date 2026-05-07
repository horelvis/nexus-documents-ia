'use client'

import Link from 'next/link'
import { AdminGuard } from '@/components/auth/admin-guard'
import { AgentBuilderForm } from '@/components/agents/agent-builder-form'

export default function NewAgentPage() {
  return (
    <AdminGuard>
      <div className="container mx-auto p-6">
        <Link href="/admin/agents" className="text-sm text-blue-600 hover:underline">
          ← Volver al catálogo
        </Link>
        <h1 className="text-2xl font-semibold my-4">Nuevo agente</h1>
        <AgentBuilderForm mode="create" />
      </div>
    </AdminGuard>
  )
}
