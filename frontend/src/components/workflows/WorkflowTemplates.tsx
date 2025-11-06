"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { FileText, UserPlus, Users, Clock, Play } from "lucide-react";
import { useWorkflows } from "@/hooks/useWorkflows";

interface WorkflowTemplatesProps {
  tenantId: string;
  onStartWorkflow: (workflowType: string, inputData: any) => Promise<void>;
}

const TEMPLATE_DATA = [
  {
    id: "contract_renewal",
    name: "Renovación de Contrato",
    description: "Proceso automatizado para renovación de contratos laborales con análisis de Emma AI",
    icon: FileText,
    color: "bg-blue-500",
    estimatedTime: "5-10 min",
    steps: 7,
    category: "HR",
    features: [
      "Análisis de rendimiento con Emma AI",
      "Evaluación de necesidad operacional",
      "Generación automática de documentos",
      "Validación legal",
      "Notificaciones a stakeholders"
    ],
  },
  {
    id: "employee_onboarding",
    name: "Incorporación de Empleado",
    description: "Proceso completo de onboarding con generación de documentos y setup de sistemas",
    icon: UserPlus,
    color: "bg-green-500",
    estimatedTime: "15-30 min",
    steps: 8,
    category: "HR",
    features: [
      "Generación de contrato de empleo",
      "Setup de cuentas de sistema",
      "Asignación de equipos",
      "Programación de sesiones de orientación",
      "Creación de plan de formación"
    ],
  },
];

export function WorkflowTemplates({ tenantId, onStartWorkflow }: WorkflowTemplatesProps) {
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);

  const handleStartTemplate = async (templateId: string) => {
    setIsStarting(true);
    try {
      // For demo purposes, we'll use sample data
      // In a real app, this would open a form or use predefined data
      const sampleData = getSampleDataForTemplate(templateId);
      await onStartWorkflow(templateId, sampleData);
      setSelectedTemplate(null);
    } catch (error) {
      console.error("Error starting template:", error);
    } finally {
      setIsStarting(false);
    }
  };

  const getSampleDataForTemplate = (templateId: string) => {
    switch (templateId) {
      case "contract_renewal":
        return {
          contract_id: `CONTRACT_${Date.now()}`,
          employee_name: "Juan Pérez García",
          contract_type: "Indefinido",
          expiration_date: "2025-12-31",
          position: "Desarrollador Senior",
          performance_rating: "Excelente",
          current_salary: "45000",
        };

      case "employee_onboarding":
        return {
          employee_id: `EMP_${Date.now()}`,
          employee_name: "María González López",
          position: "Analista de Datos",
          department: "Data & Analytics",
          start_date: "2024-02-01",
          manager_id: "MGR_001",
          contract_type: "Indefinido",
          salary: "35000",
          work_location: "Madrid Office",
          equipment_needs: ["Laptop", "Monitor externo", "Teclado ergonómico"],
        };

      default:
        return {};
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Plantillas de Workflow</h2>
        <p className="text-muted-foreground">
          Elige una plantilla predefinida para iniciar un proceso automatizado
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {TEMPLATE_DATA.map((template) => {
          const IconComponent = template.icon;
          return (
            <Card key={template.id} className="hover:shadow-lg transition-shadow">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center space-x-3">
                    <div className={`w-12 h-12 rounded-lg ${template.color} flex items-center justify-center`}>
                      <IconComponent className="h-6 w-6 text-white" />
                    </div>
                    <div>
                      <CardTitle className="text-lg">{template.name}</CardTitle>
                      <Badge variant="secondary" className="mt-1">
                        {template.category}
                      </Badge>
                    </div>
                  </div>
                </div>
                <CardDescription className="mt-2">
                  {template.description}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4">
                {/* Features */}
                <div className="space-y-2">
                  <h4 className="font-medium text-sm">Características:</h4>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    {template.features.map((feature, index) => (
                      <li key={index} className="flex items-center space-x-2">
                        <div className="w-1.5 h-1.5 bg-blue-500 rounded-full" />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Stats */}
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <div className="flex items-center space-x-1">
                    <Clock className="h-4 w-4" />
                    <span>{template.estimatedTime}</span>
                  </div>
                  <div className="flex items-center space-x-1">
                    <Users className="h-4 w-4" />
                    <span>{template.steps} pasos</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex space-x-2 pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    onClick={() => setSelectedTemplate(
                      selectedTemplate === template.id ? null : template.id
                    )}
                  >
                    Ver Detalles
                  </Button>
                  <Button
                    size="sm"
                    className="flex-1"
                    onClick={() => handleStartTemplate(template.id)}
                    disabled={isStarting}
                  >
                    {isStarting ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                        Iniciando...
                      </>
                    ) : (
                      <>
                        <Play className="h-4 w-4 mr-2" />
                        Iniciar
                      </>
                    )}
                  </Button>
                </div>

                {/* Expanded Details */}
                {selectedTemplate === template.id && (
                  <div className="mt-4 p-4 bg-gray-50 rounded-lg space-y-3">
                    <h4 className="font-medium">Proceso Detallado:</h4>
                    <div className="space-y-2 text-sm">
                      <div className="flex items-center space-x-2">
                        <div className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center text-xs font-medium">
                          1
                        </div>
                        <span>Análisis inicial y validación de datos</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <div className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center text-xs font-medium">
                          2
                        </div>
                        <span>Procesamiento con Emma AI</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <div className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center text-xs font-medium">
                          3
                        </div>
                        <span>Generación de documentos</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <div className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center text-xs font-medium">
                          4
                        </div>
                        <span>Notificaciones y seguimiento</span>
                      </div>
                    </div>

                    <div className="pt-2 border-t">
                      <p className="text-xs text-muted-foreground">
                        <strong>Tiempo estimado:</strong> {template.estimatedTime} |
                        <strong> Pasos:</strong> {template.steps} |
                        <strong> Tecnología:</strong> TemporalIO + Emma AI
                      </p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Demo Section */}
      <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold mb-2">¿Quieres probar primero?</h3>
              <p className="text-muted-foreground">
                Ejecuta una demostración del workflow de renovación de contrato con datos de ejemplo
              </p>
            </div>
            <Button
              onClick={() => handleStartTemplate("contract_renewal")}
              disabled={isStarting}
              className="bg-blue-600 hover:bg-blue-700"
            >
              {isStarting ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                  Ejecutando Demo...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 mr-2" />
                  Ejecutar Demo
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}