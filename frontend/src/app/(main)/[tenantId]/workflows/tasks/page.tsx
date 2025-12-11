"use client"

import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  ClipboardList,
  Clock,
  User,
  FileText,
  RefreshCw,
  CheckCircle,
  Hand,
  Search,
  Loader2,
  AlertCircle
} from "lucide-react"
import { useWorkflows } from "@/hooks/use-workflows"
import { useTranslation } from "@/lib/i18n/hooks"
import { WorkflowTask } from "@/lib/workflow-service"

export default function WorkflowTasksPage() {
  const params = useParams()
  const router = useRouter()
  const tenantId = params.tenantId as string
  const { t } = useTranslation()

  const [activeTab, setActiveTab] = useState("my-tasks")
  const [searchQuery, setSearchQuery] = useState("")
  const [availableTasks, setAvailableTasks] = useState<WorkflowTask[]>([])

  const {
    tasks,
    isLoading,
    error,
    refreshTasks,
    getAvailableTasks,
    completeTask,
    claimTask,
  } = useWorkflows(tenantId)

  // Load tasks on mount
  useEffect(() => {
    refreshTasks()
  }, [refreshTasks])

  // Load available tasks when tab changes
  useEffect(() => {
    if (activeTab === "available") {
      getAvailableTasks().then(setAvailableTasks)
    }
  }, [activeTab, getAvailableTasks])

  const handleClaimTask = async (taskId: string) => {
    try {
      await claimTask(taskId)
      // Refresh available tasks
      const updated = await getAvailableTasks()
      setAvailableTasks(updated)
    } catch (err) {
      console.error("Failed to claim task:", err)
    }
  }

  const handleViewTask = (taskId: string) => {
    router.push(`/${tenantId}/workflows/tasks/${taskId}`)
  }

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return "-"
    return new Date(dateStr).toLocaleString()
  }

  const getPriorityBadge = (priority: number) => {
    if (priority >= 75) return <Badge variant="destructive">Alta</Badge>
    if (priority >= 50) return <Badge variant="default">Media</Badge>
    return <Badge variant="secondary">Normal</Badge>
  }

  const filterTasks = (taskList: WorkflowTask[]) => {
    if (!searchQuery) return taskList
    const query = searchQuery.toLowerCase()
    return taskList.filter(task =>
      task.name.toLowerCase().includes(query) ||
      task.description?.toLowerCase().includes(query) ||
      task.process_instance_id.toLowerCase().includes(query)
    )
  }

  const TaskTable = ({ taskList, showClaim = false }: { taskList: WorkflowTask[]; showClaim?: boolean }) => (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Tarea</TableHead>
          <TableHead>Proceso</TableHead>
          <TableHead>Prioridad</TableHead>
          <TableHead>Creada</TableHead>
          <TableHead>Vencimiento</TableHead>
          <TableHead className="text-right">Acciones</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {filterTasks(taskList).length === 0 ? (
          <TableRow>
            <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
              No hay tareas pendientes
            </TableCell>
          </TableRow>
        ) : (
          filterTasks(taskList).map((task) => (
            <TableRow key={task.id}>
              <TableCell>
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <div className="font-medium">{task.name}</div>
                    {task.description && (
                      <div className="text-sm text-muted-foreground truncate max-w-[200px]">
                        {task.description}
                      </div>
                    )}
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <code className="text-xs bg-muted px-1 py-0.5 rounded">
                  {task.task_definition_key}
                </code>
              </TableCell>
              <TableCell>{getPriorityBadge(task.priority)}</TableCell>
              <TableCell>
                <div className="flex items-center gap-1 text-sm text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  {formatDate(task.created)}
                </div>
              </TableCell>
              <TableCell>
                {task.due ? (
                  <div className="flex items-center gap-1 text-sm">
                    <AlertCircle className="h-3 w-3 text-orange-500" />
                    {formatDate(task.due)}
                  </div>
                ) : (
                  "-"
                )}
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-2">
                  {showClaim ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleClaimTask(task.id)}
                    >
                      <Hand className="h-4 w-4 mr-1" />
                      Reclamar
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      onClick={() => handleViewTask(task.id)}
                    >
                      <CheckCircle className="h-4 w-4 mr-1" />
                      Completar
                    </Button>
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <ClipboardList className="h-8 w-8 text-blue-600" />
            Tareas Pendientes
          </h1>
          <p className="text-muted-foreground">
            Gestiona las tareas de aprobación y revisión asignadas
          </p>
        </div>
        <Button variant="outline" onClick={() => refreshTasks()}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Actualizar
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Mis Tareas</CardTitle>
            <User className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{tasks.length}</div>
            <p className="text-xs text-muted-foreground">
              Tareas asignadas a ti
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Disponibles</CardTitle>
            <Hand className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{availableTasks.length}</div>
            <p className="text-xs text-muted-foreground">
              Tareas sin asignar
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Urgentes</CardTitle>
            <AlertCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">
              {tasks.filter(t => t.priority >= 75).length}
            </div>
            <p className="text-xs text-muted-foreground">
              Con alta prioridad
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Error display */}
      {error && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="pt-6">
            <div className="flex items-center space-x-2">
              <AlertCircle className="h-5 w-5 text-red-500" />
              <span className="text-red-700">{error}</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Buscar tareas..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Task Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="my-tasks">
            Mis Tareas ({tasks.length})
          </TabsTrigger>
          <TabsTrigger value="available">
            Disponibles ({availableTasks.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="my-tasks" className="mt-6">
          <Card>
            <CardHeader>
              <CardTitle>Mis Tareas Pendientes</CardTitle>
              <CardDescription>
                Tareas asignadas a ti que requieren acción
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <TaskTable taskList={tasks} />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="available" className="mt-6">
          <Card>
            <CardHeader>
              <CardTitle>Tareas Disponibles</CardTitle>
              <CardDescription>
                Tareas sin asignar que puedes reclamar
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <TaskTable taskList={availableTasks} showClaim />
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
