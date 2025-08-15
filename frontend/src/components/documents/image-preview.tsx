"use client"

import { useState, useRef, useEffect } from 'react'
import { 
  ZoomIn, 
  ZoomOut, 
  RotateCw, 
  RotateCcw, 
  Maximize, 
  Minimize, 
  Download, 
  Move,
  RotateCcw as Reset,
  Info,
  X,
  Copy,
  Share2
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

interface ImagePreviewProps {
  src: string
  alt: string
  fileName?: string
  originalDimensions?: [number, number]
  fileSize?: number
  mimeType?: string
  className?: string
}

interface ImageMetadata {
  dimensions: [number, number]
  fileSize?: number
  mimeType?: string
  aspectRatio: string
}

export function ImagePreview({ 
  src, 
  alt, 
  fileName, 
  originalDimensions,
  fileSize,
  mimeType,
  className 
}: ImagePreviewProps) {
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showInfo, setShowInfo] = useState(false)
  const [zoom, setZoom] = useState(100)
  const [rotation, setRotation] = useState(0)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)
  const [naturalDimensions, setNaturalDimensions] = useState<[number, number] | null>(null)
  const [hasStartedLoading, setHasStartedLoading] = useState(false)

  const imageRef = useRef<HTMLImageElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Reset view when image changes
  useEffect(() => {
    setZoom(100)
    setRotation(0)
    setPosition({ x: 0, y: 0 })
    setImageLoaded(false)
    setImageError(false)
    setNaturalDimensions(null)
    setHasStartedLoading(false)
  }, [src])

  // Track when image starts loading
  useEffect(() => {
    if (src && !hasStartedLoading) {
      setHasStartedLoading(true)
    }
  }, [src, hasStartedLoading])

  const handleImageLoad = () => {
    setImageLoaded(true)
    setImageError(false)
    
    if (imageRef.current) {
      setNaturalDimensions([
        imageRef.current.naturalWidth,
        imageRef.current.naturalHeight
      ])
    }
  }

  const handleImageError = () => {
    setImageError(true)
    setImageLoaded(false)
    toast.error('Failed to load image')
  }

  const handleZoomIn = () => {
    setZoom(prev => Math.min(prev + 25, 500))
  }

  const handleZoomOut = () => {
    setZoom(prev => Math.max(prev - 25, 25))
  }

  const handleRotateRight = () => {
    setRotation(prev => (prev + 90) % 360)
  }

  const handleRotateLeft = () => {
    setRotation(prev => (prev - 90 + 360) % 360)
  }

  const handleReset = () => {
    setZoom(100)
    setRotation(0)
    setPosition({ x: 0, y: 0 })
  }

  const handleMouseDown = (e: React.MouseEvent) => {
    if (zoom > 100) {
      setIsDragging(true)
      setDragStart({
        x: e.clientX - position.x,
        y: e.clientY - position.y
      })
    }
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging && zoom > 100) {
      setPosition({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y
      })
    }
  }

  const handleMouseUp = () => {
    setIsDragging(false)
  }

  const handleDownload = async () => {
    try {
      const response = await fetch(src)
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      
      const a = document.createElement('a')
      a.href = url
      a.download = fileName || 'image'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      
      toast.success('Image downloaded successfully')
    } catch (error) {
      toast.error('Failed to download image')
    }
  }

  const handleCopyImageUrl = async () => {
    try {
      await navigator.clipboard.writeText(src)
      toast.success('Image URL copied to clipboard')
    } catch (error) {
      toast.error('Failed to copy image URL')
    }
  }

  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: fileName || 'Image',
          url: src
        })
      } catch (error) {
        // User cancelled or sharing failed
        handleCopyImageUrl()
      }
    } else {
      handleCopyImageUrl()
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const getAspectRatio = (dimensions: [number, number]) => {
    const [width, height] = dimensions
    const gcd = (a: number, b: number): number => b === 0 ? a : gcd(b, a % b)
    const divisor = gcd(width, height)
    return `${width / divisor}:${height / divisor}`
  }

  const metadata: ImageMetadata = {
    dimensions: naturalDimensions || originalDimensions || [0, 0],
    fileSize,
    mimeType,
    aspectRatio: (naturalDimensions || originalDimensions) 
      ? getAspectRatio(naturalDimensions || originalDimensions!) 
      : '0:0'
  }

  const ControlPanel = ({ isFullscreen }: { isFullscreen?: boolean }) => (
    <div className={cn(
      "flex items-center gap-2 p-2 bg-background/90 backdrop-blur-sm rounded-lg border z-10",
      isFullscreen && "fixed top-4 left-4 z-50"
    )}>
      <Button
        variant="outline"
        size="sm"
        onClick={handleZoomOut}
        disabled={zoom <= 25}
        title="Zoom Out"
      >
        <ZoomOut className="h-4 w-4" />
      </Button>
      
      <span className="text-sm font-mono min-w-[60px] text-center">
        {zoom}%
      </span>
      
      <Button
        variant="outline"
        size="sm"
        onClick={handleZoomIn}
        disabled={zoom >= 500}
        title="Zoom In"
      >
        <ZoomIn className="h-4 w-4" />
      </Button>
      
      <Separator orientation="vertical" className="h-6" />
      
      <Button
        variant="outline"
        size="sm"
        onClick={handleRotateLeft}
        title="Rotate Left"
      >
        <RotateCcw className="h-4 w-4" />
      </Button>
      
      <Button
        variant="outline"
        size="sm"
        onClick={handleRotateRight}
        title="Rotate Right"
      >
        <RotateCw className="h-4 w-4" />
      </Button>
      
      <Button
        variant="outline"
        size="sm"
        onClick={handleReset}
        title="Reset View"
      >
        <Reset className="h-4 w-4" />
      </Button>
      
      <Separator orientation="vertical" className="h-6" />
      
      <Button
        variant="outline"
        size="sm"
        onClick={() => setShowInfo(!showInfo)}
        title="Toggle Info"
      >
        <Info className="h-4 w-4" />
      </Button>
      
      {!isFullscreen && (
        <Button
          variant="outline"
          size="sm"
          onClick={() => setIsFullscreen(true)}
          title="Fullscreen"
        >
          <Maximize className="h-4 w-4" />
        </Button>
      )}
      
      <Button
        variant="outline"
        size="sm"
        onClick={handleDownload}
        title="Download"
      >
        <Download className="h-4 w-4" />
      </Button>
      
      <Button
        variant="outline"
        size="sm"
        onClick={handleShare}
        title="Share"
      >
        <Share2 className="h-4 w-4" />
      </Button>
    </div>
  )

  const ImageContainer = ({ isFullscreen }: { isFullscreen?: boolean }) => (
    <div 
      ref={containerRef}
      className={cn(
        "relative overflow-hidden bg-muted/30 rounded-lg flex items-center justify-center",
        isFullscreen ? "w-full h-full" : "w-full h-full",
        zoom > 100 && "cursor-move",
        isDragging && "cursor-grabbing"
      )}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      {hasStartedLoading && !imageLoaded && !imageError && (
        <div className="absolute inset-0 flex items-center justify-center bg-muted/30">
          <div className="flex flex-col items-center space-y-3">
            <div className="w-8 h-8 border-2 border-purple-200 border-t-purple-600 rounded-full animate-spin" />
            <div className="text-sm text-muted-foreground">Loading image...</div>
          </div>
        </div>
      )}
      
      {imageError && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center text-muted-foreground">
            <X className="h-8 w-8 mx-auto mb-2" />
            <p>Failed to load image</p>
          </div>
        </div>
      )}
      
      <img
        ref={imageRef}
        src={src}
        alt={alt}
        className={cn(
          zoom === 100 ? "max-w-full max-h-full object-contain" : "max-w-none",
          "transition-opacity duration-500 ease-out",
          imageLoaded ? "opacity-100" : "opacity-0"
        )}
        style={{
          transform: `
            translate(${position.x}px, ${position.y}px) 
            scale(${zoom / 100}) 
            rotate(${rotation}deg)
          `,
          transformOrigin: 'center center',
          transition: 'transform 0.2s ease-out, opacity 0.5s ease-out'
        }}
        onLoad={handleImageLoad}
        onError={handleImageError}
        draggable={false}
      />
      
      {zoom > 100 && imageLoaded && (
        <div className="absolute bottom-2 right-2 bg-background/90 backdrop-blur-sm rounded px-2 py-1 text-xs text-muted-foreground">
          <Move className="h-3 w-3 inline mr-1" />
          Drag to pan
        </div>
      )}
    </div>
  )

  const InfoPanel = () => (
    showInfo && (
      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-base">Image Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Dimensions:</span>
              <div className="font-mono">
                {metadata.dimensions[0]} × {metadata.dimensions[1]} px
              </div>
            </div>
            
            <div>
              <span className="text-muted-foreground">Aspect Ratio:</span>
              <div className="font-mono">{metadata.aspectRatio}</div>
            </div>
            
            {metadata.fileSize && (
              <div>
                <span className="text-muted-foreground">File Size:</span>
                <div>{formatFileSize(metadata.fileSize)}</div>
              </div>
            )}
            
            {metadata.mimeType && (
              <div>
                <span className="text-muted-foreground">Format:</span>
                <div>
                  <Badge variant="outline" className="text-xs">
                    {metadata.mimeType.split('/')[1]?.toUpperCase()}
                  </Badge>
                </div>
              </div>
            )}
            
            <div>
              <span className="text-muted-foreground">Current Zoom:</span>
              <div className="font-mono">{zoom}%</div>
            </div>
            
            <div>
              <span className="text-muted-foreground">Rotation:</span>
              <div className="font-mono">{rotation}°</div>
            </div>
          </div>
          
          {fileName && (
            <>
              <Separator />
              <div>
                <span className="text-muted-foreground">File Name:</span>
                <div className="font-mono text-sm break-all">{fileName}</div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    )
  )

  return (
    <>
      {/* Regular View */}
      <div className={cn("flex flex-col", className)}>
        <div className="flex items-center justify-end mb-4 flex-shrink-0">
          <ControlPanel />
        </div>
        
        <div className="flex-1 min-h-0 mb-4">
          <ImageContainer />
        </div>
        
        <div className="flex-shrink-0">
          <InfoPanel />
        </div>
      </div>

      {/* Fullscreen Modal */}
      <Dialog open={isFullscreen} onOpenChange={setIsFullscreen}>
        <DialogContent className="max-w-full max-h-full w-full h-full p-0 border-0">
          <div className="relative w-full h-full bg-black">
            {/* Close button */}
            <Button
              variant="outline"
              size="sm"
              className="fixed top-4 right-4 z-50 bg-background/90 backdrop-blur-sm"
              onClick={() => setIsFullscreen(false)}
              title="Exit Fullscreen"
            >
              <Minimize className="h-4 w-4" />
            </Button>
            
            {/* Controls */}
            <ControlPanel isFullscreen />
            
            {/* Image */}
            <div className="w-full h-full flex items-center justify-center p-8">
              <ImageContainer isFullscreen />
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}