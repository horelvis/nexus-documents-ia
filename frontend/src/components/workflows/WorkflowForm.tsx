"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, FileText, Users, UserPlus } from "lucide-react";

interface WorkflowFormProps {
  tenantId: string;
  onSubmit: (workflowType: string, inputData: any) => Promise<void>;
  onCancel: () => void;
}

const WORKFLOW_TYPES = [
  {
    id: "contract_renewal",
    name: "Renovación de Contrato",
    description: "Proceso automatizado para renovación de contratos laborales",
    icon: FileText,
    color: "bg-blue-500",
    fields: [
      { name: "contract_id", label: "ID del Contrato", type: "text", required: true },
      { name: "employee_name", label: "Nombre del Empleado", type: "text", required: true },
      { name: "contract_type", label: "Tipo de Contrato", type: "select", options: ["Indefinido", "Temporal", "Prácticas"], required: true },
      { name: "expiration_date", label: "Fecha de Expiración", type: "date", required: true },
      { name: "position", label: "Posición", type: "text", required: true },
      { name: "performance_rating", label: "Rating de Rendimiento", type: "select", options: ["Excelente", "Bueno", "Regular", "Deficiente"], required: false },
      { name: "current_salary", label: "Salario Actual", type: "text", required: false },
    ],
  },
  {
    id: "employee_onboarding",
    name: "Incorporación de Empleado",
    description: "Proceso completo de onboarding y setup inicial",
    icon: UserPlus,
    color: "bg-green-500",
    fields: [
      { name: "employee_id", label: "ID del Empleado", type: "text", required: true },
      { name: "employee_name", label: "Nombre del Empleado", type: "text", required: true },
      { name: "position", label: "Posición", type: "text", required: true },
      { name: "department", label: "Departamento", type: "text", required: true },
      { name: "start_date", label: "Fecha de Inicio", type: "date", required: true },
      { name: "manager_id", label: "ID del Manager", type: "text", required: true },
      { name: "contract_type", label: "Tipo de Contrato", type: "select", options: ["Indefinido", "Temporal", "Prácticas"], required: true },
      { name: "salary", label: "Salario", type: "text", required: true },
      { name: "work_location", label: "Ubicación de Trabajo", type: "text", required: true },
      { name: "equipment_needs", label: "Equipos Necesarios", type: "textarea", placeholder: "Lista de equipos separados por comas", required: false },
    ],
  },
];

export function WorkflowForm({ tenantId, onSubmit, onCancel }: WorkflowFormProps) {
  const [selectedWorkflowType, setSelectedWorkflowType] = useState<string>("");
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const selectedWorkflow = WORKFLOW_TYPES.find(w => w.id === selectedWorkflowType);

  const handleInputChange = (fieldName: string, value: any) => {
    setFormData(prev => ({
      ...prev,
      [fieldName]: value,
    }));

    // Clear error for this field
    if (errors[fieldName]) {
      setErrors(prev => ({
        ...prev,
        [fieldName]: "",
      }));
    }
  };

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!selectedWorkflowType) {
      newErrors.workflowType = "Debes seleccionar un tipo de workflow";
      return newErrors;
    }

    selectedWorkflow?.fields.forEach(field => {
      if (field.required && !formData[field.name]?.trim()) {
        newErrors[field.name] = `${field.label} es requerido`;
      }
    });

    return newErrors;
  };

  const handleSubmit = async () => {
    const validationErrors = validateForm();

    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setIsSubmitting(true);
    try {
      // Add tenant_id and user_id to form data
      const submitData = {
        ...formData,
        tenant_id: tenantId,
        user_id: "current_user", // TODO: Get from auth context
        hr_user_id: "current_user", // For onboarding workflows
      };

      // Process equipment_needs for onboarding
      if (selectedWorkflowType === "employee_onboarding" && formData.equipment_needs) {
        submitData.equipment_needs = formData.equipment_needs
          .split(",")
          .map((item: string) => item.trim())
          .filter((item: string) => item.length > 0);
      }

      await onSubmit(selectedWorkflowType, submitData);
    } catch (error) {
      console.error("Error submitting workflow:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderField = (field: any) => {
    const value = formData[field.name] || "";
    const error = errors[field.name];

    switch (field.type) {
      case "select":
        return (
          <div key={field.name} className="space-y-2">
            <Label htmlFor={field.name}>
              {field.label}
              {field.required && <span className="text-red-500 ml-1">*</span>}
            </Label>
            <Select
              value={value}
              onValueChange={(newValue) => handleInputChange(field.name, newValue)}
            >
              <SelectTrigger>
                <SelectValue placeholder={`Seleccionar ${field.label.toLowerCase()}`} />
              </SelectTrigger>
              <SelectContent>
                {field.options.map((option: string) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {error && <p className="text-sm text-red-500">{error}</p>}
          </div>
        );

      case "textarea":
        return (
          <div key={field.name} className="space-y-2">
            <Label htmlFor={field.name}>
              {field.label}
              {field.required && <span className="text-red-500 ml-1">*</span>}
            </Label>
            <Textarea
              id={field.name}
              value={value}
              onChange={(e) => handleInputChange(field.name, e.target.value)}
              placeholder={field.placeholder}
              className={error ? "border-red-500" : ""}
            />
            {error && <p className="text-sm text-red-500">{error}</p>}
          </div>
        );

      default:
        return (
          <div key={field.name} className="space-y-2">
            <Label htmlFor={field.name}>
              {field.label}
              {field.required && <span className="text-red-500 ml-1">*</span>}
            </Label>
            <Input
              id={field.name}
              type={field.type}
              value={value}
              onChange={(e) => handleInputChange(field.name, e.target.value)}
              className={error ? "border-red-500" : ""}
            />
            {error && <p className="text-sm text-red-500">{error}</p>}
          </div>
        );
    }
  };

  return (
    <Dialog open={true} onOpenChange={() => onCancel()}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Iniciar Nuevo Workflow</DialogTitle>
          <DialogDescription>
            Selecciona el tipo de workflow y completa la información requerida
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Workflow Type Selection */}
          {!selectedWorkflowType ? (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Seleccionar Tipo de Workflow</h3>
              <div className="grid gap-4">
                {WORKFLOW_TYPES.map((workflow) => {
                  const IconComponent = workflow.icon;
                  return (
                    <Card
                      key={workflow.id}
                      className="cursor-pointer hover:shadow-md transition-shadow"
                      onClick={() => setSelectedWorkflowType(workflow.id)}
                    >
                      <CardContent className="p-4">
                        <div className="flex items-center space-x-4">
                          <div className={`w-12 h-12 rounded-lg ${workflow.color} flex items-center justify-center`}>
                            <IconComponent className="h-6 w-6 text-white" />
                          </div>
                          <div className="flex-1">
                            <h4 className="font-semibold">{workflow.name}</h4>
                            <p className="text-sm text-muted-foreground">{workflow.description}</p>
                          </div>
                          <Badge variant="secondary">
                            {workflow.fields.length} campos
                          </Badge>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
              {errors.workflowType && (
                <p className="text-sm text-red-500">{errors.workflowType}</p>
              )}
            </div>
          ) : (
            /* Form */
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  {selectedWorkflow && (
                    <>
                      <div className={`w-10 h-10 rounded-lg ${selectedWorkflow.color} flex items-center justify-center`}>
                        <selectedWorkflow.icon className="h-5 w-5 text-white" />
                      </div>
                      <div>
                        <h3 className="font-semibold">{selectedWorkflow.name}</h3>
                        <p className="text-sm text-muted-foreground">{selectedWorkflow.description}</p>
                      </div>
                    </>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedWorkflowType("")}
                >
                  Cambiar Tipo
                </Button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {selectedWorkflow?.fields.map(renderField)}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end space-x-3 pt-4 border-t">
            <Button variant="outline" onClick={onCancel}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={isSubmitting || !selectedWorkflowType}
            >
              {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {isSubmitting ? "Iniciando..." : "Iniciar Workflow"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}