import { useState, useEffect, useRef } from 'react'

/**
 * useStreamingText — Progressive text reveal for AI responses.
 *
 * When `targetText` changes (new content arrives), this hook reveals
 * the text incrementally (word-by-word) to simulate streaming.
 *
 * If text is already being revealed and new content extends the target
 * (real streaming via SDK messages events), it catches up smoothly.
 *
 * When `enabled` is false, returns targetText immediately (no animation).
 */
export function useStreamingText(
  targetText: string,
  enabled: boolean,
  /** Words per tick (higher = faster reveal) */
  wordsPerTick = 3,
  /** ms between reveal ticks */
  intervalMs = 30,
): { displayText: string; isRevealing: boolean } {
  const [revealedCount, setRevealedCount] = useState(0)
  const prevTargetRef = useRef('')
  const wordsRef = useRef<string[]>([])

  // Split target into words (preserve whitespace by splitting on word boundaries)
  useEffect(() => {
    if (!enabled || !targetText) {
      wordsRef.current = []
      setRevealedCount(0)
      prevTargetRef.current = ''
      return
    }

    // If the new target extends the previous one (real streaming), just update words
    // If it's completely new, reset reveal from scratch
    const isExtension = targetText.startsWith(prevTargetRef.current) && prevTargetRef.current.length > 0
    prevTargetRef.current = targetText

    const words = targetText.split(/(\s+)/).filter(Boolean)
    wordsRef.current = words

    if (!isExtension) {
      // New text — start reveal from beginning
      setRevealedCount(0)
    }
    // If extension, keep current revealedCount — the interval will catch up
  }, [targetText, enabled])

  // Interval to progressively reveal words
  useEffect(() => {
    if (!enabled) return
    const totalWords = wordsRef.current.length
    if (revealedCount >= totalWords) return

    const timer = setInterval(() => {
      setRevealedCount((prev) => {
        const next = Math.min(prev + wordsPerTick, wordsRef.current.length)
        if (next >= wordsRef.current.length) {
          clearInterval(timer)
        }
        return next
      })
    }, intervalMs)

    return () => clearInterval(timer)
  }, [enabled, revealedCount, wordsPerTick, intervalMs, targetText])

  if (!enabled || !targetText) {
    return { displayText: targetText, isRevealing: false }
  }

  const totalWords = wordsRef.current.length
  const isRevealing = revealedCount < totalWords
  const displayText = isRevealing
    ? wordsRef.current.slice(0, revealedCount).join('')
    : targetText

  return { displayText, isRevealing }
}
