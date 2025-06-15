'use client'

import { useState } from 'react'
import { useAuth } from '@clerk/nextjs'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Loader2 } from 'lucide-react'

export function StripeDebug() {
  const { getToken } = useAuth()
  const [debugData, setDebugData] = useState<any>(null)
  const [syncData, setSyncData] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(false)

  const testStripeConnection = async () => {
    setIsLoading(true)
    try {
      const token = await getToken()
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      
      // Test debug endpoint
      const debugResponse = await fetch(`${API_BASE}/api/v1/stripe/debug-stripe`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      })
      
      if (debugResponse.ok) {
        const data = await debugResponse.json()
        setDebugData(data)
      } else {
        setDebugData({ error: 'Failed to fetch debug data' })
      }
      
      // Test sync endpoint
      const syncResponse = await fetch(`${API_BASE}/api/v1/stripe/sync-subscription`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        }
      })
      
      if (syncResponse.ok) {
        const data = await syncResponse.json()
        setSyncData(data)
      } else {
        const error = await syncResponse.text()
        setSyncData({ error })
      }
      
    } catch (error) {
      console.error('Debug error:', error)
      setDebugData({ error: error.message })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Stripe Debug</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Button 
          onClick={testStripeConnection} 
          disabled={isLoading}
          variant="outline"
        >
          {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Test Stripe Connection
        </Button>
        
        {debugData && (
          <div className="mt-4 p-4 bg-gray-100 rounded-lg">
            <h4 className="font-semibold mb-2">Debug Data:</h4>
            <pre className="text-xs overflow-auto">
              {JSON.stringify(debugData, null, 2)}
            </pre>
          </div>
        )}
        
        {syncData && (
          <div className="mt-4 p-4 bg-blue-50 rounded-lg">
            <h4 className="font-semibold mb-2">Sync Result:</h4>
            <pre className="text-xs overflow-auto">
              {JSON.stringify(syncData, null, 2)}
            </pre>
          </div>
        )}
      </CardContent>
    </Card>
  )
}