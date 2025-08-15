'use client'

import { useAuth } from '@clerk/nextjs'
import { useCallback, useRef } from 'react'

interface TokenCache {
  token: string | null
  expiry: number
}

export function useAuthToken() {
  const { getToken } = useAuth()
  const tokenCacheRef = useRef<TokenCache>({ token: null, expiry: 0 })

  const getValidToken = useCallback(async (maxRetries = 3): Promise<string | null> => {
    // Check if cached token is still valid (with 30 second buffer)
    const now = Date.now()
    const buffer = 30 * 1000 // 30 seconds
    
    if (tokenCacheRef.current.token && tokenCacheRef.current.expiry > now + buffer) {
      return tokenCacheRef.current.token
    }

    // Get fresh token with retry logic
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        console.log(`Getting fresh token (attempt ${attempt + 1}/${maxRetries})`)
        
        // Request token with reasonable expiration (5 minutes)
        const token = await getToken({ 
          template: undefined, // Use default template
          leeway: 60 // 60 seconds leeway for clock skew
        })
        
        if (token) {
          // Parse JWT to get expiry (basic parsing)
          try {
            const [, payload] = token.split('.')
            const decoded = JSON.parse(atob(payload))
            const expiry = decoded.exp * 1000 // Convert to milliseconds
            
            // Cache the token
            tokenCacheRef.current = { token, expiry }
            
            console.log(`Token obtained, expires at: ${new Date(expiry).toISOString()}`)
            return token
          } catch (parseError) {
            console.warn('Could not parse token expiry, using token without caching')
            return token
          }
        }
      } catch (error) {
        console.warn(`Token fetch attempt ${attempt + 1} failed:`, error)
        
        if (attempt < maxRetries - 1) {
          // Wait progressively longer between retries
          const delay = Math.min(1000 * Math.pow(2, attempt), 5000)
          await new Promise(resolve => setTimeout(resolve, delay))
        }
      }
    }

    console.error('Failed to obtain valid token after all retries')
    return null
  }, [getToken])

  const invalidateToken = useCallback(() => {
    console.log('Invalidating cached token')
    tokenCacheRef.current = { token: null, expiry: 0 }
  }, [])

  return {
    getValidToken,
    invalidateToken
  }
}