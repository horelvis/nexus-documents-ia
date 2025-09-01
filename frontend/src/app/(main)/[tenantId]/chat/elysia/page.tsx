import { Metadata } from "next"
import { ElysiaChat } from "@/components/elysia-chat"

export const metadata: Metadata = {
  title: "Elysia AI Assistant",
  description: "Chat inteligente con capacidades agentic RAG powered by Elysia",
}

interface ElysiaPageProps {
  params: {
    tenantId: string
  }
}

export default function ElysiaPage({ params }: ElysiaPageProps) {
  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Elysia AI Assistant</h1>
        <p className="text-muted-foreground">
          Asistente inteligente con capacidades agentic RAG para análisis de documentos
        </p>
      </div>

      {/* Chat Component */}
      <div className="max-w-4xl mx-auto">
        <ElysiaChat 
          tenantId={params.tenantId}
          className="h-[800px]"
          initialMessage="¡Hola! Soy Elysia, tu asistente inteligente. ¿En qué puedo ayudarte hoy?"
        />
      </div>

      {/* Features Info */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto mt-8">
        <div className="p-4 border rounded-lg">
          <h3 className="font-semibold mb-2">🧠 Agentic RAG</h3>
          <p className="text-sm text-muted-foreground">
            Utiliza un sistema de decisiones inteligente para encontrar la información más relevante
          </p>
        </div>
        <div className="p-4 border rounded-lg">
          <h3 className="font-semibold mb-2">📚 Búsqueda Contextual</h3>
          <p className="text-sm text-muted-foreground">
            Busca automáticamente en tus documentos y proporciona respuestas contextuales
          </p>
        </div>
        <div className="p-4 border rounded-lg">
          <h3 className="font-semibold mb-2">⚡ Tiempo Real</h3>
          <p className="text-sm text-muted-foreground">
            Respuestas rápidas con transparencia total del proceso de decisión
          </p>
        </div>
      </div>
    </div>
  )
}