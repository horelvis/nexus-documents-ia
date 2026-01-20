"use client"

import { UnifiedLoader, InitialLoader, PageTransitionLoader, InlineLoader, MinimalSpinner } from "./unified-loader"

/**
 * Componente principal del loader de Nexus con la "N" redonda
 * Muestra el logo de Nexus (N) en el centro de círculos giratorios
 */
export function NexusLoader({
  size = "md",
  text = "Cargando...",
  subtext,
  fullScreen = true
}: {
  size?: "sm" | "md" | "lg"
  text?: string
  subtext?: string
  fullScreen?: boolean
}) {
  return (
    <UnifiedLoader
      variant="page"
      size={size}
      text={text}
      subtext={subtext}
      showLogo={true}
      fullScreen={fullScreen}
    />
  )
}

/**
 * Loader para carga inicial de la aplicación
 */
export function NexusInitialLoader() {
  return (
    <UnifiedLoader
      variant="initial"
      size="lg"
      text="Nexus Document System"
      subtext="Inicializando..."
      showLogo={true}
      fullScreen={true}
    />
  )
}

/**
 * Loader pequeño para uso inline
 */
export function NexusInlineLoader({ text }: { text?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-8">
      <MinimalSpinner size="sm" />
      {text && <span className="text-sm text-muted-foreground">{text}</span>}
    </div>
  )
}

/**
 * Loader para transiciones de página
 */
export function NexusPageLoader({ text = "Cargando página..." }: { text?: string }) {
  return (
    <UnifiedLoader
      variant="page"
      size="md"
      text={text}
      subtext="Por favor espera un momento"
      showLogo={true}
      fullScreen={true}
    />
  )
}

/**
 * Loader para el chat/asistente virtual
 */
export function NexusChatLoader({ text = "Procesando..." }: { text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 space-y-4">
      <UnifiedLoader
        variant="minimal"
        size="md"
        showLogo={true}
        fullScreen={false}
      />
      <div className="text-center space-y-1">
        <p className="text-sm font-medium text-purple-600 dark:text-purple-400">
          {text}
        </p>
        <p className="text-xs text-muted-foreground">
          El asistente está trabajando en tu solicitud
        </p>
      </div>
    </div>
  )
}

/**
 * Loader para operaciones de documentos
 */
export function NexusDocumentLoader({ 
  action = "Procesando documento...",
  progress 
}: { 
  action?: string
  progress?: number 
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 space-y-6">
      <UnifiedLoader
        variant="minimal"
        size="lg"
        showLogo={true}
        fullScreen={false}
      />
      <div className="text-center space-y-2">
        <p className="text-base font-medium">{action}</p>
        {progress !== undefined && (
          <div className="w-64 bg-gray-200 dark:bg-gray-700 rounded-full h-2">
            <div 
              className="bg-purple-600 h-2 rounded-full transition-all duration-300 ease-out"
              style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
            />
          </div>
        )}
        {progress !== undefined && (
          <p className="text-xs text-muted-foreground">
            {Math.round(progress)}% completado
          </p>
        )}
      </div>
    </div>
  )
}

// Export del componente principal como default
export default NexusLoader