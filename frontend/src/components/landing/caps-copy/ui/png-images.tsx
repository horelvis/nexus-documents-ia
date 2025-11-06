import Image from "next/image";
import { LucideProps } from "lucide-react";

interface StaticImageProps extends Omit<LucideProps, 'width' | 'height'> {
  width?: number;
  height?: number;
  src: string;
  alt: string;
  type?: 'png' | 'jpg' | 'svg';
}

const StaticImage = ({ className, width = 1512, height = 982, src, alt, type = 'jpg', ...props }: StaticImageProps) => {
  // Para SVG, usar img tag para mantener escalabilidad
  if (type === 'svg') {
    return (
      <img
        src={src}
        alt={alt}
        className={`w-full h-full object-contain ${className || ''}`}
        {...props}
      />
    );
  }

  // Para JPG/PNG, usar next/image para optimización
  return (
    <div className={className} {...props}>
      <Image
        src={src}
        alt={alt}
        width={width}
        height={height}
        className="w-full h-full object-contain"
        priority
        quality={90}
      />
    </div>
  );
};

const StaticImages = {
  // Dashboard - usar JPG para mejor compresión con gradientes
  dashboard: (props: LucideProps) => (
    <StaticImage
      {...props}
      src="/images/dashboard.jpg"
      alt="Dashboard"
      width={1512}
      height={982}
      type="jpg"
    />
  ),
  
  // Leftboard - usar SVG para mejor escalabilidad
  leftboard: (props: LucideProps) => (
    <StaticImage
      {...props}
      src="/images/leftboard.svg"
      alt="Left Board"
      type="svg"
    />
  ),
  
  // Rightboard - usar SVG para mejor escalabilidad
  rightboard: (props: LucideProps) => (
    <StaticImage
      {...props}
      src="/images/rightboard.svg"
      alt="Right Board"
      type="svg"
    />
  ),
};

export default StaticImages;