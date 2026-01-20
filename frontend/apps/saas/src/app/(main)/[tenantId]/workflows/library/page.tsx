"use client"

import { useState, use } from "react"
import Link from "next/link"
import { 
  IconBook, 
  IconUsers, 
  IconClockPlay,
  IconCircleCheck,
  IconTrendingUp,
  IconDownload,
  IconEye,
  IconCopy,
  IconStar,
  IconSearch,
  IconFilter
} from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

interface ProcessTemplate {
  id: string
  name: string
  description: string
  category: string
  icon: any
  color: string
  estimatedTime: string
  steps: number
  usage: number
  rating: number
  lastUpdated: string
  tags: string[]
  complexity: "simple" | "intermediate" | "advanced"
}

export default function ProcessLibraryPage({ params }: { params: Promise<{ tenantId: string }> }) {
  const resolvedParams = use(params)
  const [searchTerm, setSearchTerm] = useState("")
  const [selectedCategory, setSelectedCategory] = useState("all")
  const [selectedComplexity, setSelectedComplexity] = useState("all")

  const templates: ProcessTemplate[] = [
    {
      id: "contract_renewal",
      name: "Renovación de Contratos",
      description: "Proceso completo para renovar contratos laborales con validación legal automática",
      category: "hr",
      icon: IconUsers,
      color: "bg-blue-500",
      estimatedTime: "15 días",
      steps: 8,
      usage: 45,
      rating: 4.8,
      lastUpdated: "2024-12-15",
      tags: ["contratos", "rrhh", "legal", "automatizado"],
      complexity: "intermediate"
    },
    {
      id: "contract_termination",
      name: "Terminación de Contratos",
      description: "Gestión de terminaciones laborales con cálculo automático de liquidaciones",
      category: "hr",
      icon: IconClockPlay,
      color: "bg-red-500",
      estimatedTime: "10 días",
      steps: 6,
      usage: 23,
      rating: 4.6,
      lastUpdated: "2024-12-10",
      tags: ["terminación", "liquidación", "legal"],
      complexity: "advanced"
    },
    {
      id: "employee_onboarding",
      name: "Onboarding de Empleados",
      description: "Proceso de incorporación completo desde la contratación hasta la integración",
      category: "hr",
      icon: IconCircleCheck,
      color: "bg-green-500",
      estimatedTime: "7 días",
      steps: 10,
      usage: 67,
      rating: 4.9,
      lastUpdated: "2024-12-18",
      tags: ["onboarding", "integración", "documentación"],
      complexity: "simple"
    },
    {
      id: "performance_review",
      name: "Evaluación de Desempeño",
      description: "Sistema de evaluaciones periódicas con feedback 360° y planes de mejora",
      category: "performance",
      icon: IconTrendingUp,
      color: "bg-purple-500",
      estimatedTime: "21 días",
      steps: 7,
      usage: 34,
      rating: 4.7,
      lastUpdated: "2024-12-05",
      tags: ["evaluación", "feedback", "desarrollo"],
      complexity: "intermediate"
    },
    {
      id: "leave_request",
      name: "Solicitudes de Permisos",
      description: "Gestión automatizada de solicitudes de vacaciones, permisos y ausencias",
      category: "operations",
      icon: IconClockPlay,
      color: "bg-orange-500",
      estimatedTime: "3 días",
      steps: 4,
      usage: 89,
      rating: 4.5,
      lastUpdated: "2024-12-20",
      tags: ["permisos", "vacaciones", "ausencias"],
      complexity: "simple"
    },
    {
      id: "disciplinary_process",
      name: "Proceso Disciplinario",
      description: "Gestión de medidas disciplinarias con garantías procesales y registro detallado",
      category: "legal",
      icon: IconUsers,
      color: "bg-yellow-500",
      estimatedTime: "30 días",
      steps: 9,
      usage: 12,
      rating: 4.4,
      lastUpdated: "2024-11-28",
      tags: ["disciplinario", "legal", "procedimiento"],
      complexity: "advanced"
    }
  ]

  const categories = [
    { value: "all", label: "Todas las Categorías" },
    { value: "hr", label: "Recursos Humanos" },
    { value: "performance", label: "Desempeño" },
    { value: "operations", label: "Operaciones" },
    { value: "legal", label: "Legal" }
  ]

  const complexityLevels = [
    { value: "all", label: "Todos los Niveles" },
    { value: "simple", label: "Simple" },
    { value: "intermediate", label: "Intermedio" },
    { value: "advanced", label: "Avanzado" }
  ]

  const filteredTemplates = templates.filter(template => {
    const matchesSearch = template.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         template.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         template.tags.some(tag => tag.toLowerCase().includes(searchTerm.toLowerCase()))
    
    const matchesCategory = selectedCategory === "all" || template.category === selectedCategory
    const matchesComplexity = selectedComplexity === "all" || template.complexity === selectedComplexity
    
    return matchesSearch && matchesCategory && matchesComplexity
  })

  const getComplexityColor = (complexity: string) => {
    switch (complexity) {
      case "simple": return "text-green-600 bg-green-100"
      case "intermediate": return "text-yellow-600 bg-yellow-100"
      case "advanced": return "text-red-600 bg-red-100"
      default: return "text-gray-600 bg-gray-100"
    }
  }

  const renderStars = (rating: number) => {
    return Array.from({ length: 5 }, (_, i) => (
      <IconStar 
        key={i} 
        className={`h-3 w-3 ${i < Math.floor(rating) ? 'text-yellow-400 fill-current' : 'text-gray-300'}`} 
      />
    ))
  }

  return (
    <div className="container mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <IconBook className="h-8 w-8 text-blue-600" />
            Biblioteca de Procesos
          </h1>
          <p className="text-muted-foreground mt-1">
            Plantillas predefinidas y optimizadas para procesos laborales comunes
          </p>
        </div>
        <div className="flex gap-3">
          <Button asChild variant="outline">
            <Link href={`/${resolvedParams.tenantId}/workflows/builder`}>
              Crear Personalizado
            </Link>
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1">
              <div className="relative">
                <IconSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input 
                  placeholder="Buscar procesos..."
                  className="pl-10"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
            </div>
            
            <Select value={selectedCategory} onValueChange={setSelectedCategory}>
              <SelectTrigger className="w-[200px]">
                <IconFilter className="h-4 w-4 mr-2" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {categories.map((category) => (
                  <SelectItem key={category.value} value={category.value}>
                    {category.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={selectedComplexity} onValueChange={setSelectedComplexity}>
              <SelectTrigger className="w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {complexityLevels.map((level) => (
                  <SelectItem key={level.value} value={level.value}>
                    {level.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Templates Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredTemplates.map((template) => (
          <Card key={template.id} className="hover:shadow-md transition-shadow">
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className={`w-12 h-12 rounded-lg ${template.color} flex items-center justify-center mb-3`}>
                  <template.icon className="h-6 w-6 text-white" />
                </div>
                <Badge className={getComplexityColor(template.complexity)}>
                  {template.complexity === "simple" ? "Simple" : 
                   template.complexity === "intermediate" ? "Intermedio" : "Avanzado"}
                </Badge>
              </div>
              
              <CardTitle className="text-lg">{template.name}</CardTitle>
              <CardDescription>{template.description}</CardDescription>
            </CardHeader>
            
            <CardContent className="space-y-4">
              {/* Stats */}
              <div className="grid grid-cols-3 gap-2 text-center">
                <div>
                  <div className="text-lg font-semibold text-blue-600">{template.steps}</div>
                  <div className="text-xs text-muted-foreground">Pasos</div>
                </div>
                <div>
                  <div className="text-lg font-semibold text-green-600">{template.usage}</div>
                  <div className="text-xs text-muted-foreground">Usos</div>
                </div>
                <div>
                  <div className="text-lg font-semibold text-purple-600">{template.estimatedTime}</div>
                  <div className="text-xs text-muted-foreground">Duración</div>
                </div>
              </div>

              {/* Rating */}
              <div className="flex items-center justify-center gap-2">
                <div className="flex">{renderStars(template.rating)}</div>
                <span className="text-sm text-muted-foreground">({template.rating})</span>
              </div>

              {/* Tags */}
              <div className="flex flex-wrap gap-1">
                {template.tags.slice(0, 3).map((tag) => (
                  <Badge key={tag} variant="secondary" className="text-xs">
                    {tag}
                  </Badge>
                ))}
                {template.tags.length > 3 && (
                  <Badge variant="secondary" className="text-xs">
                    +{template.tags.length - 3}
                  </Badge>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-2">
                <Button size="sm" className="flex-1" asChild>
                  <Link href={`/${resolvedParams.tenantId}/workflows/${template.id}`}>
                    <IconEye className="h-3 w-3 mr-1" />
                    Ver
                  </Link>
                </Button>
                <Button size="sm" variant="outline">
                  <IconCopy className="h-3 w-3 mr-1" />
                  Clonar
                </Button>
                <Button size="sm" variant="outline">
                  <IconDownload className="h-3 w-3" />
                </Button>
              </div>

              {/* Last Updated */}
              <div className="text-xs text-muted-foreground text-center pt-2 border-t">
                Actualizado: {template.lastUpdated}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* No results */}
      {filteredTemplates.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <IconBook className="h-16 w-16 text-gray-300 mb-4" />
            <p className="text-gray-500 mb-2">No se encontraron procesos</p>
            <p className="text-sm text-muted-foreground text-center">
              Intenta con diferentes filtros o crea un proceso personalizado
            </p>
            <Button asChild className="mt-4" variant="outline">
              <Link href={`/${resolvedParams.tenantId}/workflows/builder`}>
                Crear Proceso Personalizado
              </Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Stats Summary */}
      <Card className="bg-gradient-to-r from-blue-50 to-cyan-50 border-blue-200">
        <CardContent className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold text-blue-600">{templates.length}</div>
              <p className="text-sm text-muted-foreground">Plantillas Disponibles</p>
            </div>
            <div>
              <div className="text-2xl font-bold text-green-600">
                {templates.reduce((acc, t) => acc + t.usage, 0)}
              </div>
              <p className="text-sm text-muted-foreground">Usos Totales</p>
            </div>
            <div>
              <div className="text-2xl font-bold text-purple-600">
                {(templates.reduce((acc, t) => acc + t.rating, 0) / templates.length).toFixed(1)}
              </div>
              <p className="text-sm text-muted-foreground">Rating Promedio</p>
            </div>
            <div>
              <div className="text-2xl font-bold text-orange-600">95%</div>
              <p className="text-sm text-muted-foreground">Satisfacción</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}