import { LogoSpinner } from './logo-spinner'

interface LoadingScreenProps {
  title?: string
  subtitle?: string
}

export function LoadingScreen({
  title = 'NouxCube AI',
  subtitle = 'Cargando...'
}: LoadingScreenProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#05070d]">
      {/* Background effects */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-[500px] bg-gradient-to-b from-cyan-500/8 via-transparent to-transparent" />
        <div className="absolute right-0 top-1/4 h-[600px] w-[600px] rounded-full bg-cyan-500/5 blur-[120px]" />
      </div>

      <div className="relative flex flex-col items-center gap-4">
        <LogoSpinner size="lg" />

        <div className="flex flex-col items-center gap-1">
          <p className="text-lg font-medium text-white">{title}</p>
          <p className="text-sm text-slate-400">{subtitle}</p>
        </div>
      </div>
    </div>
  )
}
