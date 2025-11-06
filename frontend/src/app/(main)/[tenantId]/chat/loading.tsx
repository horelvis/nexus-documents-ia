import { NexusChatLoader } from "@/components/ui/nexus-loader"

export default function ChatLoading() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <NexusChatLoader text="Iniciando chat con IA..." />
    </div>
  )
}