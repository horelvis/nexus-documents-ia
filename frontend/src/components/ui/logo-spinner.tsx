import Image from 'next/image'

interface LogoSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
}

const sizes = {
  sm: { logo: 40, className: 'h-10', glow: '-inset-3', bar: 'w-24' },
  md: { logo: 56, className: 'h-14', glow: '-inset-4', bar: 'w-28' },
  lg: { logo: 64, className: 'h-16', glow: '-inset-4', bar: 'w-32' },
}

export function LogoSpinner({ size = 'md' }: LogoSpinnerProps) {
  const { logo, className, glow, bar } = sizes[size]

  return (
    <div className="flex flex-col items-center gap-5">
      <div className="relative">
        <div className={`absolute ${glow} rounded-full bg-cyan-500/20 blur-xl`} />
        <Image
          src="/logo-single.png"
          alt="NouxCube AI"
          width={logo}
          height={logo}
          className={`relative ${className} w-auto`}
          priority
        />
      </div>
      <div className={`h-1 ${bar} overflow-hidden rounded-full bg-white/10`}>
        <div className="h-full w-1/2 animate-[shimmer_1.5s_ease-in-out_infinite] rounded-full bg-gradient-to-r from-transparent via-cyan-400 to-transparent" />
      </div>
    </div>
  )
}
