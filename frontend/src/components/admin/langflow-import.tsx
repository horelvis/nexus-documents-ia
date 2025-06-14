"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  IconUpload,
  IconLink,
  IconCheck,
  IconAlertCircle,
  IconLoader2,
  IconRobot,
  IconSparkles
} from "@tabler/icons-react"
import { useNotifications } from "@/contexts/notifications-context"

interface LangflowImportProps {
  onImportSuccess?: (agent: any) => void
}

export default function LangflowImport({ onImportSuccess }: LangflowImportProps) {
  const [isImporting, setIsImporting] = useState(false)
  const [importMethod, setImportMethod] = useState<"json" | "url">("json")
  const [jsonData, setJsonData] = useState("")
  const [flowUrl, setFlowUrl] = useState("")
  const [isPublic, setIsPublic] = useState(false)
  const [autoDeploy, setAutoDeploy] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const { addNotification } = useNotifications()

  const handleImport = async () => {
    setIsImporting(true)
    setError(null)
    setSuccess(null)

    try {
      let response
      
      if (importMethod === "json") {
        // Validate JSON
        let parsedJson
        try {
          parsedJson = JSON.parse(jsonData)
        } catch (e) {
          throw new Error("Invalid JSON format")
        }

        response = await fetch("/api/v1/agent-registry/import/langflow", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            langflow_data: parsedJson,
            is_public: isPublic,
            auto_deploy: autoDeploy
          })
        })
      } else {
        // Import from URL
        if (!flowUrl.trim()) {
          throw new Error("Please enter a valid URL")
        }

        response = await fetch("/api/v1/agent-registry/import/langflow-url", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            flow_url: flowUrl,
            is_public: isPublic,
            auto_deploy: autoDeploy
          })
        })
      }

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || "Import failed")
      }

      const result = await response.json()
      
      setSuccess(`Successfully imported agent: ${result.agent.display_name}`)
      addNotification({
        type: "success",
        title: "Agent Imported",
        message: `${result.agent.display_name} has been imported from Langflow`
      })

      // Clear form
      setJsonData("")
      setFlowUrl("")
      
      // Callback
      if (onImportSuccess) {
        onImportSuccess(result.agent)
      }

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Import failed"
      setError(errorMessage)
      addNotification({
        type: "error",
        title: "Import Failed",
        message: errorMessage
      })
    } finally {
      setIsImporting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconSparkles className="h-5 w-5" />
          Import from Langflow
        </CardTitle>
        <CardDescription>
          Import agent flows created in Langflow visual builder
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Tabs value={importMethod} onValueChange={(v) => setImportMethod(v as "json" | "url")}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="json" className="flex items-center gap-2">
              <IconUpload className="h-4 w-4" />
              JSON Export
            </TabsTrigger>
            <TabsTrigger value="url" className="flex items-center gap-2">
              <IconLink className="h-4 w-4" />
              URL Import
            </TabsTrigger>
          </TabsList>

          <TabsContent value="json" className="space-y-4">
            <div>
              <Label htmlFor="json-data">Langflow Export JSON</Label>
              <Textarea
                id="json-data"
                placeholder={`Paste your Langflow export JSON here...
{
  "name": "My Flow",
  "description": "Flow description",
  "data": {
    "nodes": [...],
    "edges": [...]
  }
}`}
                value={jsonData}
                onChange={(e) => setJsonData(e.target.value)}
                className="min-h-[200px] font-mono text-xs"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Export your flow from Langflow and paste the JSON here
              </p>
            </div>
          </TabsContent>

          <TabsContent value="url" className="space-y-4">
            <div>
              <Label htmlFor="flow-url">Langflow API URL</Label>
              <Input
                id="flow-url"
                type="url"
                placeholder="https://langflow.example.com/api/flows/abc123"
                value={flowUrl}
                onChange={(e) => setFlowUrl(e.target.value)}
              />
              <p className="text-xs text-muted-foreground mt-1">
                Enter the API URL of your Langflow instance
              </p>
            </div>
          </TabsContent>
        </Tabs>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="public">Public Agent</Label>
              <p className="text-xs text-muted-foreground">
                Make this agent available to all tenants
              </p>
            </div>
            <Switch
              id="public"
              checked={isPublic}
              onCheckedChange={setIsPublic}
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="deploy">Auto Deploy</Label>
              <p className="text-xs text-muted-foreground">
                Automatically deploy agent after import
              </p>
            </div>
            <Switch
              id="deploy"
              checked={autoDeploy}
              onCheckedChange={setAutoDeploy}
            />
          </div>
        </div>

        {error && (
          <Alert variant="destructive">
            <IconAlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {success && (
          <Alert>
            <IconCheck className="h-4 w-4" />
            <AlertDescription>{success}</AlertDescription>
          </Alert>
        )}

        <Button
          onClick={handleImport}
          disabled={isImporting || (importMethod === "json" ? !jsonData.trim() : !flowUrl.trim())}
          className="w-full"
        >
          {isImporting ? (
            <>
              <IconLoader2 className="h-4 w-4 mr-2 animate-spin" />
              Importing...
            </>
          ) : (
            <>
              <IconRobot className="h-4 w-4 mr-2" />
              Import Agent
            </>
          )}
        </Button>

        <div className="rounded-lg bg-muted p-4">
          <h4 className="font-medium text-sm mb-2">How it works:</h4>
          <ol className="text-xs space-y-1 text-muted-foreground">
            <li>1. Create your agent flow in Langflow</li>
            <li>2. Export the flow as JSON or get the API URL</li>
            <li>3. Import it here to make it available in your system</li>
            <li>4. The agent will be converted and ready to use</li>
          </ol>
        </div>
      </CardContent>
    </Card>
  )
}