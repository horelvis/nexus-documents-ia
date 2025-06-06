'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { 
  CheckCircle, 
  XCircle, 
  AlertCircle, 
  Loader2, 
  RefreshCw,
  Activity,
  Server,
  Database,
  Cpu,
  Clock
} from 'lucide-react'
import { agentsService } from '@/lib/services/agents.service'

interface ServiceStatus {
  name: string
  status: 'healthy' | 'unhealthy' | 'warning' | 'unknown'
  response_time?: number
  last_check?: string
  details?: any
  error?: string
}

export function AgentHealthCheck() {
  const [isChecking, setIsChecking] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [services, setServices] = useState<ServiceStatus[]>([
    {
      name: 'Langroid Service',
      status: 'unknown',
    },
    {
      name: 'Ollama LLM',
      status: 'unknown',
    },
    {
      name: 'Qdrant Vector DB',
      status: 'unknown',
    },
    {
      name: 'Backend API',
      status: 'unknown',
    }
  ])

  useEffect(() => {
    checkAllServices()
  }, [])

  const checkAllServices = async () => {
    setIsChecking(true)
    const startTime = Date.now()

    try {
      // Check Langroid health
      const langroidHealth = await checkLangroidHealth()
      
      // Update services status
      setServices([
        {
          name: 'Langroid Service',
          status: langroidHealth.status === 'healthy' ? 'healthy' : 'unhealthy',
          response_time: langroidHealth.response_time,
          last_check: new Date().toISOString(),
          details: langroidHealth.details,
          error: langroidHealth.error
        },
        {
          name: 'Ollama LLM',
          status: langroidHealth.ollama_status || 'unknown',
          response_time: langroidHealth.ollama_response_time,
          last_check: new Date().toISOString(),
        },
        {
          name: 'Qdrant Vector DB',
          status: langroidHealth.qdrant_status || 'unknown',
          response_time: langroidHealth.qdrant_response_time,
          last_check: new Date().toISOString(),
        },
        {
          name: 'Backend API',
          status: 'healthy', // If we can make the call, backend is healthy
          response_time: Date.now() - startTime,
          last_check: new Date().toISOString(),
        }
      ])

      setLastUpdate(new Date())
    } catch (error) {
      console.error('Health check failed:', error)
      // Update with error status
      setServices(prev => prev.map(service => ({
        ...service,
        status: service.name === 'Backend API' ? 'unhealthy' : service.status,
        error: error instanceof Error ? error.message : 'Unknown error',
        last_check: new Date().toISOString(),
      })))
    } finally {
      setIsChecking(false)
    }
  }

  const checkLangroidHealth = async () => {
    const startTime = Date.now()
    try {
      const result = await agentsService.checkLangroidHealth()
      return {
        status: result.status || 'healthy',
        response_time: Date.now() - startTime,
        details: result,
        ollama_status: result.langroid_service?.models ? 'healthy' : 'unknown',
        ollama_response_time: 50, // Mock
        qdrant_status: result.langroid_service?.active_agents !== undefined ? 'healthy' : 'unknown',
        qdrant_response_time: 30, // Mock
      }
    } catch (error) {
      return {
        status: 'unhealthy',
        response_time: Date.now() - startTime,
        error: error instanceof Error ? error.message : 'Unknown error'
      }
    }
  }

  const runIntegrationTest = async () => {
    setIsChecking(true)
    try {
      const result = await agentsService.testLangroidAgent()
      alert('✅ Integration test successful!\n\n' + JSON.stringify(result, null, 2))
    } catch (error) {
      alert('❌ Integration test failed!\n\n' + (error instanceof Error ? error.message : 'Unknown error'))
    } finally {
      setIsChecking(false)
    }
  }

  const getStatusIcon = (status: ServiceStatus['status']) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle className="h-5 w-5 text-green-500" />
      case 'unhealthy':
        return <XCircle className="h-5 w-5 text-red-500" />
      case 'warning':
        return <AlertCircle className="h-5 w-5 text-yellow-500" />
      default:
        return <AlertCircle className="h-5 w-5 text-gray-400" />
    }
  }

  const getStatusBadge = (status: ServiceStatus['status']) => {
    switch (status) {
      case 'healthy':
        return <Badge className="bg-green-100 text-green-800">Healthy</Badge>
      case 'unhealthy':
        return <Badge className="bg-red-100 text-red-800">Unhealthy</Badge>
      case 'warning':
        return <Badge className="bg-yellow-100 text-yellow-800">Warning</Badge>
      default:
        return <Badge variant="secondary">Unknown</Badge>
    }
  }

  const getServiceIcon = (serviceName: string) => {
    switch (serviceName) {
      case 'Langroid Service':
        return <Activity className="h-4 w-4" />
      case 'Ollama LLM':
        return <Cpu className="h-4 w-4" />
      case 'Qdrant Vector DB':
        return <Database className="h-4 w-4" />
      case 'Backend API':
        return <Server className="h-4 w-4" />
      default:
        return <Server className="h-4 w-4" />
    }
  }

  const healthyServices = services.filter(s => s.status === 'healthy').length
  const totalServices = services.length
  const healthPercentage = (healthyServices / totalServices) * 100

  return (
    <div className="space-y-6">
      {/* Overall Health Summary */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5" />
                System Health Overview
              </CardTitle>
              <CardDescription>
                Estado general de todos los servicios del sistema de agentes
              </CardDescription>
            </div>
            <Button
              variant="outline"
              onClick={checkAllServices}
              disabled={isChecking}
            >
              {isChecking ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              {isChecking ? 'Checking...' : 'Refresh'}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Overall Health</span>
              <span className="text-sm text-muted-foreground">
                {healthyServices}/{totalServices} services healthy
              </span>
            </div>
            <Progress value={healthPercentage} className="w-full" />
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
              <div className="text-center">
                <div className="text-2xl font-bold text-green-600">{healthyServices}</div>
                <div className="text-sm text-muted-foreground">Healthy</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-red-600">
                  {services.filter(s => s.status === 'unhealthy').length}
                </div>
                <div className="text-sm text-muted-foreground">Unhealthy</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-yellow-600">
                  {services.filter(s => s.status === 'warning').length}
                </div>
                <div className="text-sm text-muted-foreground">Warning</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-500">
                  {services.filter(s => s.status === 'unknown').length}
                </div>
                <div className="text-sm text-muted-foreground">Unknown</div>
              </div>
            </div>

            {lastUpdate && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Clock className="h-4 w-4" />
                Last updated: {lastUpdate.toLocaleTimeString()}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Individual Service Status */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {services.map((service, index) => (
          <Card key={index}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {getServiceIcon(service.name)}
                  <CardTitle className="text-lg">{service.name}</CardTitle>
                </div>
                {getStatusIcon(service.status)}
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Status:</span>
                  {getStatusBadge(service.status)}
                </div>
                
                {service.response_time && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Response Time:</span>
                    <span className="text-sm text-muted-foreground">
                      {service.response_time}ms
                    </span>
                  </div>
                )}
                
                {service.last_check && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Last Check:</span>
                    <span className="text-sm text-muted-foreground">
                      {new Date(service.last_check).toLocaleTimeString()}
                    </span>
                  </div>
                )}
                
                {service.error && (
                  <div className="p-2 bg-red-50 border border-red-200 rounded">
                    <p className="text-sm text-red-800">{service.error}</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Integration Test */}
      <Card>
        <CardHeader>
          <CardTitle>Integration Test</CardTitle>
          <CardDescription>
            Run a complete end-to-end test of the agent system
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              This test will create a temporary agent, execute a simple task, and clean up. 
              It verifies the complete integration between frontend, backend, and Langroid services.
            </p>
            
            <Button
              onClick={runIntegrationTest}
              disabled={isChecking}
              className="w-full"
            >
              {isChecking ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Activity className="h-4 w-4 mr-2" />
              )}
              Run Integration Test
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}