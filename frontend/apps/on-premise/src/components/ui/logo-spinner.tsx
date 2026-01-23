import Image from 'next/image'

interface LogoSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  showRings?: boolean
}

const sizes = {
  sm: { logo: 40, className: 'h-10' },
  md: { logo: 56, className: 'h-14' },
  lg: { logo: 80, className: 'h-20' },
}

export function LogoSpinner({ size = 'md', showRings = true }: LogoSpinnerProps) {
  const { logo, className } = sizes[size]

  return (
    <div className="relative">
      {showRings && (
        <>
          <div className="absolute -inset-4 animate-ping rounded-full bg-cyan-400/20 [animation-duration:2s]" />
          <div className="absolute -inset-6 animate-pulse rounded-full bg-cyan-500/10" />
        </>
      )}
      <div className="absolute -inset-4 rounded-full bg-cyan-500/20 blur-xl" />
      <Image
        src="/logo-single.png"
        alt="NouxCube AI"
        width={logo}
        height={logo}
        className={`relative ${className} w-auto animate-pulse`}
        priority
      />
    </div>
  )
}
