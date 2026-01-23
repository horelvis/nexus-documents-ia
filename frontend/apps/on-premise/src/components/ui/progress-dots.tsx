interface ProgressDotsProps {
  className?: string
}

export function ProgressDots({ className = '' }: ProgressDotsProps) {
  return (
    <div className={`flex gap-1.5 ${className}`}>
      <span className="h-2 w-2 animate-bounce rounded-full bg-cyan-400 [animation-delay:-0.3s]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-cyan-400 [animation-delay:-0.15s]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-cyan-400" />
    </div>
  )
}
