"use client"

import { useEffect, useRef } from 'react'
import { AudioVisualizerProps } from './types'

export function AudioVisualizer({ analyser, isActive, color = "#60a5fa" }: AudioVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const requestRef = useRef<number | null>(null)
  const rotationRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1

    const updateSize = () => {
      const rect = canvas.getBoundingClientRect()
      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
      ctx.scale(dpr, dpr)
      return { width: rect.width, height: rect.height }
    }

    let dimensions = updateSize()

    const observer = new ResizeObserver(() => {
       dimensions = updateSize()
    })
    observer.observe(canvas)

    // Configuration
    const BAR_COUNT = 64
    const SECTIONS = BAR_COUNT / 2 // 32 unique bands, mirrored

    // Helper function for rounded rectangles
    const roundRect = (
      ctx: CanvasRenderingContext2D,
      x: number,
      y: number,
      w: number,
      h: number,
      r: number
    ) => {
      if (w < 2 * r) r = w / 2
      if (h < 2 * r) r = h / 2
      ctx.beginPath()
      ctx.moveTo(x + r, y)
      ctx.arcTo(x + w, y, x + w, y + h, r)
      ctx.arcTo(x + w, y + h, x, y + h, r)
      ctx.arcTo(x, y + h, x, y, r)
      ctx.arcTo(x, y, x + w, y, r)
      ctx.closePath()
    }

    const render = () => {
      const { width, height } = dimensions
      ctx.clearRect(0, 0, width, height)

      // Neon glow effect
      ctx.globalCompositeOperation = 'screen'

      // Smooth rotation only when active
      if (isActive) {
        rotationRef.current += 0.002
      } else {
        rotationRef.current = 0
      }

      // Get and process frequency data
      const effectiveData = new Float32Array(SECTIONS)

      if (analyser && isActive) {
        const bufferLength = analyser.frequencyBinCount
        const rawData = new Uint8Array(bufferLength)
        analyser.getByteFrequencyData(rawData)

        // Focus on vocal range (first ~60% of bins)
        const usefulBinCount = Math.floor(bufferLength * 0.6)
        const step = usefulBinCount / SECTIONS

        for (let i = 0; i < SECTIONS; i++) {
          const startBin = Math.floor(i * step)
          const endBin = Math.floor((i + 1) * step)
          let sum = 0
          let count = 0

          for (let j = startBin; j < endBin; j++) {
            sum += rawData[j] || 0
            count++
          }
          const avg = count > 0 ? sum / count : 0

          // Visual equalization: boost higher frequencies
          const trebleBoost = 1 + (i / SECTIONS) * 1.5
          effectiveData[i] = Math.min(avg * trebleBoost, 255)
        }
      }

      const cx = width / 2
      const cy = height / 2
      const radius = Math.min(width, height) * 0.25 // Responsive radius
      const MAX_BAR_HEIGHT = Math.min(width, height) * 0.28

      // Uniform breathing for static mode
      const staticBreath = Math.sin(performance.now() * 0.003) * 3

      for (let i = 0; i < BAR_COUNT; i++) {
        let barHeight = 0

        // Mirror logic for perfect symmetry
        let dataIndex = i
        if (i >= SECTIONS) {
          dataIndex = BAR_COUNT - 1 - i
        }

        if (isActive) {
          const val = effectiveData[dataIndex] || 0
          const normalizedAmp = Math.pow(val / 255, 2.5)
          barHeight = normalizedAmp * MAX_BAR_HEIGHT
          barHeight = Math.max(barHeight, 4)
        } else {
          // Idle mode: fixed height + uniform breathing
          barHeight = 6 + staticBreath
        }

        // Radial position
        const angleStep = (Math.PI * 2) / BAR_COUNT
        const angle = i * angleStep + rotationRef.current - (Math.PI / 2)

        const x = cx + Math.cos(angle) * radius
        const y = cy + Math.sin(angle) * radius

        // Color gradient (cyan -> blue -> purple)
        const hue = 170 + (i / BAR_COUNT) * 140
        const barColor = `hsl(${hue}, 100%, 60%)`

        ctx.save()
        ctx.translate(x, y)
        ctx.rotate(angle)

        ctx.fillStyle = barColor

        // Thin elegant bars
        const w = (2 * Math.PI * radius / BAR_COUNT) * 0.3

        roundRect(ctx, 0, -w/2, barHeight, w, w/2)

        // Subtle glow
        if (isActive) {
          const val = effectiveData[dataIndex] || 0
          const normalizedAmp = Math.pow(val / 255, 2)
          ctx.shadowBlur = 10 * normalizedAmp
          ctx.shadowColor = barColor
        } else {
          ctx.shadowBlur = 0
        }

        ctx.fill()
        ctx.restore()
      }

      requestRef.current = requestAnimationFrame(render)
    }

    render()

    return () => {
      observer.disconnect()
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current)
      }
    }
  }, [analyser, isActive, color])

  return (
    <canvas
      ref={canvasRef}
      className="w-full h-full"
      style={{ minHeight: '200px' }}
    />
  )
}
