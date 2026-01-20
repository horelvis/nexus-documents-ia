"use client"

import { FormEvent, useState } from 'react'
import { Loader2, Sparkles, Building2, Mail, Users, MessageSquare } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { cn } from '@/lib/utils'

type DemoRequestDialogProps = {
  open: boolean
  onOpenChange: (value: boolean) => void
}

export function DemoRequestDialog({ open, onOpenChange }: DemoRequestDialogProps) {
  const { toast } = useToast()
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    company: '',
    teamSize: '1-10',
    useCase: 'asesoria',
    notes: '',
  })

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)

    try {
      // Simular envío; conectar con API de leads si está disponible
      await new Promise((resolve) => setTimeout(resolve, 900))

      toast({
        title: 'Solicitud enviada',
        description: 'Te contactaremos en menos de 1 día hábil para agendar la demo.',
      })
      setFormData({
        name: '',
        email: '',
        company: '',
        teamSize: '1-10',
        useCase: 'asesoria',
        notes: '',
      })
      onOpenChange(false)
    } catch (error) {
      console.error('Error sending demo request', error)
      toast({
        title: 'No se pudo enviar la solicitud',
        description: 'Inténtalo nuevamente o contáctanos en hola@nexus.com',
        variant: 'destructive',
      })
    } finally {
      setLoading(false)
    }
  }

  const updateField = (field: keyof typeof formData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl border-white/10 bg-[#0c1222]/95 text-white shadow-2xl">
        <DialogHeader className="gap-1">
          <DialogTitle className="text-2xl font-semibold text-white flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-cyan-300" />
            Solicita una demo
          </DialogTitle>
          <DialogDescription className="text-slate-300">
            Cuéntanos sobre tu equipo y coordinaremos una sesión personalizada con un especialista.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="name" className="flex items-center gap-2 text-slate-200">
              <Sparkles className="h-4 w-4 text-cyan-300" />
              Nombre y apellidos
            </Label>
            <Input
              id="name"
              required
              value={formData.name}
              onChange={(e) => updateField('name', e.target.value)}
              className="bg-[#0b1220] border-white/10 text-white"
              placeholder="Ana Gómez"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email" className="flex items-center gap-2 text-slate-200">
              <Mail className="h-4 w-4 text-cyan-300" />
              Correo de trabajo
            </Label>
            <Input
              id="email"
              type="email"
              required
              value={formData.email}
              onChange={(e) => updateField('email', e.target.value)}
              className="bg-[#0b1220] border-white/10 text-white"
              placeholder="ana@empresa.com"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="company" className="flex items-center gap-2 text-slate-200">
              <Building2 className="h-4 w-4 text-cyan-300" />
              Empresa
            </Label>
            <Input
              id="company"
              value={formData.company}
              onChange={(e) => updateField('company', e.target.value)}
              className="bg-[#0b1220] border-white/10 text-white"
              placeholder="Nexus Legal"
            />
          </div>

          <div className="space-y-2">
            <Label className="flex items-center gap-2 text-slate-200">
              <Users className="h-4 w-4 text-cyan-300" />
              Tamaño del equipo
            </Label>
            <Select value={formData.teamSize} onValueChange={(value) => updateField('teamSize', value)}>
              <SelectTrigger className="bg-[#0b1220] border-white/10 text-white">
                <SelectValue placeholder="Selecciona" />
              </SelectTrigger>
              <SelectContent className="bg-[#0b1220] text-white border-white/10">
                <SelectItem value="1-10">1-10 personas</SelectItem>
                <SelectItem value="10-50">10-50 personas</SelectItem>
                <SelectItem value="50-200">50-200 personas</SelectItem>
                <SelectItem value="200+">200+ personas</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2 md:col-span-2">
            <Label className="flex items-center gap-2 text-slate-200">
              <MessageSquare className="h-4 w-4 text-cyan-300" />
              Caso de uso principal
            </Label>
            <Select value={formData.useCase} onValueChange={(value) => updateField('useCase', value)}>
              <SelectTrigger className="bg-[#0b1220] border-white/10 text-white">
                <SelectValue placeholder="Selecciona" />
              </SelectTrigger>
              <SelectContent className="bg-[#0b1220] text-white border-white/10">
                <SelectItem value="asesoria">Asesoría laboral / cumplimiento</SelectItem>
                <SelectItem value="contratos">Gestión y firma de contratos</SelectItem>
                <SelectItem value="documental">Repositorio y búsqueda de expedientes</SelectItem>
                <SelectItem value="otro">Otro</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="notes" className="flex items-center gap-2 text-slate-200">
              <Sparkles className="h-4 w-4 text-cyan-300" />
              ¿Qué te gustaría lograr en la demo?
            </Label>
            <Textarea
              id="notes"
              value={formData.notes}
              onChange={(e) => updateField('notes', e.target.value)}
              className="min-h-[100px] bg-[#0b1220] border-white/10 text-white"
              placeholder="Ej. evaluar flujo de firmas, migrar archivos, probar búsquedas con IA"
            />
          </div>

          <div className="md:col-span-2 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <p className="text-sm text-slate-300">
              Un especialista te escribirá para coordinar agenda y configurar un entorno piloto.
            </p>
            <Button
              type="submit"
              className={cn('w-full md:w-auto bg-cyan-400 text-slate-900 hover:bg-cyan-300', {
                'opacity-80': loading,
              })}
              disabled={loading}
            >
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Enviar solicitud
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
