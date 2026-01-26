'use client'

/**
 * TemplateSelector - Presentation Template Selector with Preview
 *
 * Allows users to select presentation templates with visual previews.
 * Includes built-in templates and external templates from Slidesgo.
 */

import { useState } from 'react'
import {
  IconCheck,
  IconExternalLink,
  IconEye,
  IconBuilding,
  IconSchool,
  IconSparkles,
  IconPalette,
  IconRocket,
  IconArrowLeft,
} from '@tabler/icons-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Button,
  ScrollArea,
  Badge,
} from '@nexus/shared/ui'
import { cn } from '@/lib/utils'
import { PresentationTemplate } from '@/lib/services/notebook.service'

// =====================================
// Template Data
// =====================================

export interface TemplateInfo {
  id: PresentationTemplate | string
  name: string
  description: string
  category: 'corporate' | 'educational' | 'creative' | 'minimal' | 'startup'
  previewUrl: string
  thumbnailUrl: string
  source: 'built-in' | 'slidesgo' | 'canva' | 'external'
  sourceUrl?: string
  isPremium?: boolean
  tags: string[]
}

// Default fallback colors for templates (used when image fails to load)
const TEMPLATE_FALLBACK_COLORS: Record<string, string> = {
  corporate: '#005A9C',   // Blue
  educational: '#2E7D32', // Green
  minimal: '#757575',     // Gray
  creative: '#7B1FA2',    // Purple
  nouxcube: '#1E3A5F',    // Dark blue
}

export const PRESENTATION_TEMPLATES: TemplateInfo[] = [
  // Built-in Templates - Local images with fallback
  {
    id: 'corporate',
    name: 'Corporativo Animado',
    description: 'Diseño profesional con animaciones sutiles para presentaciones de impacto',
    category: 'corporate',
    previewUrl: '/templates/corporate-preview.png',
    thumbnailUrl: '/templates/corporate-thumb.png',
    source: 'built-in',
    tags: ['animado', 'profesional', 'negocios'],
  },
  {
    id: 'educational',
    name: 'Educativo Timeline',
    description: 'Plantilla con línea temporal ideal para contenido educativo y formación',
    category: 'educational',
    previewUrl: '/templates/educational-preview.png',
    thumbnailUrl: '/templates/educational-thumb.png',
    source: 'built-in',
    tags: ['timeline', 'formación', 'académico'],
  },
  {
    id: 'minimal',
    name: 'Minimalista Clean',
    description: 'Diseño limpio y elegante que destaca el contenido sobre el diseño',
    category: 'minimal',
    previewUrl: '/templates/minimal-preview.png',
    thumbnailUrl: '/templates/minimal-thumb.png',
    source: 'built-in',
    tags: ['limpio', 'elegante', 'simple'],
  },
  {
    id: 'creative',
    name: 'Infográfico Creativo',
    description: 'Infografías animadas con diseño colorido y llamativo para datos visuales',
    category: 'creative',
    previewUrl: '/templates/creative-preview.png',
    thumbnailUrl: '/templates/creative-thumb.png',
    source: 'built-in',
    tags: ['infografía', 'colorido', 'datos'],
  },
  {
    id: 'nouxcube',
    name: 'NouxCube Brand',
    description: 'Plantilla oficial con identidad visual NouxCube (azul oscuro)',
    category: 'corporate',
    previewUrl: '/templates/nouxcube-preview.png',
    thumbnailUrl: '/templates/nouxcube-thumb.png',
    source: 'built-in',
    tags: ['marca', 'IA', 'tecnología'],
  },

  // Slidesgo Templates - Corporate
  {
    id: 'slidesgo-corporate-strategy',
    name: 'Corporate Strategy',
    description: 'Toolkit versátil para estrategias empresariales',
    category: 'corporate',
    previewUrl: 'https://slidesgo.com/theme/corporate-strategy-consulting-toolkit',
    thumbnailUrl: 'https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=400&h=225&fit=crop',
    source: 'slidesgo',
    sourceUrl: 'https://slidesgo.com/theme/corporate-strategy-consulting-toolkit',
    tags: ['estrategia', 'consultoría', 'toolkit'],
  },
  {
    id: 'slidesgo-business-annual',
    name: 'Business Annual Report',
    description: 'Para reportes anuales y análisis de negocio',
    category: 'corporate',
    previewUrl: 'https://slidesgo.com/theme/business-annual-report',
    thumbnailUrl: 'https://images.unsplash.com/photo-1554224155-6726b3ff858f?w=400&h=225&fit=crop',
    source: 'slidesgo',
    sourceUrl: 'https://slidesgo.com/theme/business-annual-report',
    tags: ['reporte', 'anual', 'análisis'],
  },
  {
    id: 'slidesgo-management-consulting',
    name: 'Management Consulting',
    description: 'Para presentar servicios de consultoría',
    category: 'corporate',
    previewUrl: 'https://slidesgo.com/theme/management-consulting-toolkit',
    thumbnailUrl: 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=400&h=225&fit=crop',
    source: 'slidesgo',
    sourceUrl: 'https://slidesgo.com/theme/management-consulting-toolkit',
    tags: ['consultoría', 'gestión', 'servicios'],
  },

  // Slidesgo Templates - Startup/Tech
  {
    id: 'slidesgo-tech-startup',
    name: 'Tech Startup',
    description: 'Moderno y futurista para startups tecnológicas',
    category: 'startup',
    previewUrl: 'https://slidesgo.com/theme/tech-startup-professional',
    thumbnailUrl: 'https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=400&h=225&fit=crop',
    source: 'slidesgo',
    sourceUrl: 'https://slidesgo.com/theme/tech-startup-professional',
    tags: ['startup', 'tecnología', 'pitch'],
  },
  {
    id: 'slidesgo-investment-plan',
    name: 'Investment Business Plan',
    description: 'Para pitch decks y planes de inversión',
    category: 'startup',
    previewUrl: 'https://slidesgo.com/theme/investment-business-plan',
    thumbnailUrl: 'https://images.unsplash.com/photo-1559526324-4b87b5e36e44?w=400&h=225&fit=crop',
    source: 'slidesgo',
    sourceUrl: 'https://slidesgo.com/theme/investment-business-plan',
    tags: ['inversión', 'pitch', 'startup'],
  },

  // Slidesgo Templates - Minimal
  {
    id: 'slidesgo-minimalist-business',
    name: 'Minimalist Business',
    description: 'Elegancia y simplicidad para ejecutivos',
    category: 'minimal',
    previewUrl: 'https://slidesgo.com/theme/minimalist-business-slides',
    thumbnailUrl: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=225&fit=crop',
    source: 'slidesgo',
    sourceUrl: 'https://slidesgo.com/theme/minimalist-business-slides',
    tags: ['minimalista', 'elegante', 'ejecutivo'],
  },
  {
    id: 'slidesgo-elegant-bw',
    name: 'Elegant Black & White',
    description: 'Sofisticado diseño en escala de grises',
    category: 'minimal',
    previewUrl: 'https://slidesgo.com/theme/elegant-black-white-thesis-defense',
    thumbnailUrl: 'https://images.unsplash.com/photo-1494438639946-1ebd1d20bf85?w=400&h=225&fit=crop',
    source: 'slidesgo',
    sourceUrl: 'https://slidesgo.com/theme/elegant-black-white-thesis-defense',
    tags: ['elegante', 'formal', 'b&w'],
  },

  // Slidesgo Templates - Creative
  {
    id: 'slidesgo-creative-portfolio',
    name: 'Creative Portfolio',
    description: 'Para portfolios y proyectos creativos',
    category: 'creative',
    previewUrl: 'https://slidesgo.com/theme/creative-portfolio',
    thumbnailUrl: 'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=400&h=225&fit=crop',
    source: 'slidesgo',
    sourceUrl: 'https://slidesgo.com/search/creative',
    tags: ['portfolio', 'creativo', 'diseño'],
  },

  // Slidesgo Templates - Educational
  {
    id: 'slidesgo-educational-workshop',
    name: 'Educational Workshop',
    description: 'Para talleres y sesiones de formación',
    category: 'educational',
    previewUrl: 'https://slidesgo.com/education',
    thumbnailUrl: 'https://images.unsplash.com/photo-1524178232363-1fb2b075b655?w=400&h=225&fit=crop',
    source: 'slidesgo',
    sourceUrl: 'https://slidesgo.com/education',
    tags: ['taller', 'formación', 'workshop'],
  },
]

// Category icons and labels
const CATEGORY_CONFIG = {
  corporate: { icon: IconBuilding, label: 'Corporativo', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
  educational: { icon: IconSchool, label: 'Educativo', color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
  creative: { icon: IconPalette, label: 'Creativo', color: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400' },
  minimal: { icon: IconSparkles, label: 'Minimalista', color: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400' },
  startup: { icon: IconRocket, label: 'Startup', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' },
} as const

type CategoryKey = keyof typeof CATEGORY_CONFIG

// =====================================
// Template Card Component
// =====================================

interface TemplateCardProps {
  template: TemplateInfo
  isSelected: boolean
  onSelect: () => void
  onPreview: () => void
}

function TemplateCard({ template, isSelected, onSelect, onPreview }: TemplateCardProps) {
  const [imageError, setImageError] = useState(false)
  const config = CATEGORY_CONFIG[template.category]
  const CategoryIcon = config.icon
  const fallbackColor = TEMPLATE_FALLBACK_COLORS[template.id] || '#666666'

  return (
    <div
      className={cn(
        "relative group rounded-lg border-2 overflow-hidden cursor-pointer transition-all",
        isSelected
          ? "border-primary ring-2 ring-primary/20"
          : "border-transparent hover:border-muted-foreground/20"
      )}
      onClick={onSelect}
    >
      {/* Thumbnail */}
      <div className="aspect-video relative bg-muted">
        {imageError ? (
          // Fallback: colored placeholder with template name
          <div
            className="w-full h-full flex items-center justify-center"
            style={{ backgroundColor: fallbackColor }}
          >
            <div className="text-center text-white p-2">
              <CategoryIcon className="h-8 w-8 mx-auto mb-1 opacity-80" />
              <span className="text-xs font-medium opacity-90">{template.name}</span>
            </div>
          </div>
        ) : (
          <img
            src={template.thumbnailUrl}
            alt={template.name}
            className="w-full h-full object-cover"
            loading="lazy"
            onError={() => setImageError(true)}
          />
        )}

        {/* Overlay on hover */}
        <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            className="h-7 text-xs"
            onClick={(e) => {
              e.stopPropagation()
              onPreview()
            }}
          >
            <IconEye className="h-3.5 w-3.5 mr-1" />
            Preview
          </Button>
          {template.sourceUrl && (
            <Button
              variant="secondary"
              size="sm"
              className="h-7 text-xs"
              onClick={(e) => {
                e.stopPropagation()
                window.open(template.sourceUrl, '_blank')
              }}
            >
              <IconExternalLink className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>

        {/* Selected indicator */}
        {isSelected && (
          <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-primary flex items-center justify-center">
            <IconCheck className="h-3 w-3 text-primary-foreground" />
          </div>
        )}

        {/* Source badge */}
        {template.source !== 'built-in' && (
          <Badge
            variant="secondary"
            className="absolute top-2 left-2 text-[10px] py-0 h-5"
          >
            {template.source === 'slidesgo' ? 'Slidesgo' : template.source}
          </Badge>
        )}
      </div>

      {/* Info */}
      <div className="p-2">
        <div className="flex items-center gap-1.5 mb-0.5">
          <CategoryIcon className="h-3 w-3 text-muted-foreground" />
          <span className="text-xs font-medium truncate">{template.name}</span>
        </div>
        <p className="text-[10px] text-muted-foreground line-clamp-2">
          {template.description}
        </p>
      </div>
    </div>
  )
}

// =====================================
// Preview View Component (inside dialog)
// =====================================

interface PreviewViewProps {
  template: TemplateInfo
  onBack: () => void
  onSelect: () => void
}

function PreviewView({ template, onBack, onSelect }: PreviewViewProps) {
  const config = CATEGORY_CONFIG[template.category]
  const CategoryIcon = config.icon

  return (
    <div className="space-y-4">
      {/* Back button */}
      <Button variant="ghost" size="sm" onClick={onBack} className="h-7 text-xs -ml-2">
        <IconArrowLeft className="h-3.5 w-3.5 mr-1" />
        Volver
      </Button>

      {/* Header */}
      <div className="flex items-center gap-2">
        <CategoryIcon className="h-5 w-5" />
        <h3 className="font-semibold">{template.name}</h3>
      </div>

      {/* Large preview */}
      <div className="aspect-video rounded-lg overflow-hidden bg-muted">
        <img
          src={template.thumbnailUrl}
          alt={template.name}
          className="w-full h-full object-cover"
        />
      </div>

      {/* Info */}
      <div className="space-y-2">
        <p className="text-sm text-muted-foreground">{template.description}</p>

        <div className="flex items-center gap-2 flex-wrap">
          <Badge className={config.color}>
            {config.label}
          </Badge>
          {template.tags.map((tag) => (
            <Badge key={tag} variant="outline" className="text-xs">
              {tag}
            </Badge>
          ))}
        </div>

        {template.sourceUrl && (
          <a
            href={template.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            Ver en {template.source === 'slidesgo' ? 'Slidesgo' : 'sitio externo'}
            <IconExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" onClick={onBack}>
          Cancelar
        </Button>
        {template.source === 'built-in' && (
          <Button onClick={onSelect}>
            <IconCheck className="h-4 w-4 mr-1.5" />
            Usar esta plantilla
          </Button>
        )}
      </div>
    </div>
  )
}

// =====================================
// Main Template Selector Component
// =====================================

interface TemplateSelectorProps {
  selectedTemplate: PresentationTemplate | string
  onSelect: (templateId: PresentationTemplate | string) => void
  compact?: boolean
}

export function TemplateSelector({
  selectedTemplate,
  onSelect,
  compact = false,
}: TemplateSelectorProps) {
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [previewTemplate, setPreviewTemplate] = useState<TemplateInfo | null>(null)
  const [activeCategory, setActiveCategory] = useState<CategoryKey | null>(null)

  const selectedTemplateInfo = PRESENTATION_TEMPLATES.find(t => t.id === selectedTemplate)

  // Filter templates by category
  const filteredTemplates = activeCategory
    ? PRESENTATION_TEMPLATES.filter(t => t.category === activeCategory)
    : PRESENTATION_TEMPLATES

  const handleSelect = (templateId: string) => {
    const template = PRESENTATION_TEMPLATES.find(t => t.id === templateId)
    if (template?.source === 'built-in') {
      onSelect(templateId as PresentationTemplate)
      setIsDialogOpen(false)
      setPreviewTemplate(null)
    }
  }

  const handlePreview = (template: TemplateInfo) => {
    setPreviewTemplate(template)
  }

  const handleBackFromPreview = () => {
    setPreviewTemplate(null)
  }

  const handleDialogClose = () => {
    setIsDialogOpen(false)
    setPreviewTemplate(null)
  }

  // Get display info for the trigger button
  const getTriggerContent = () => {
    if (!selectedTemplateInfo) {
      return <span>Seleccionar plantilla</span>
    }
    const Icon = CATEGORY_CONFIG[selectedTemplateInfo.category].icon
    return (
      <>
        <Icon className="h-3 w-3" />
        <span>{selectedTemplateInfo.name}</span>
      </>
    )
  }

  // Compact mode - show a button that opens the dialog
  if (compact) {
    return (
      <Dialog open={isDialogOpen} onOpenChange={(open) => {
        if (!open) handleDialogClose()
        else setIsDialogOpen(true)
      }}>
        <DialogTrigger asChild>
          <Button variant="outline" className="w-full h-7 text-xs justify-between">
            <span className="flex items-center gap-1.5">
              {getTriggerContent()}
            </span>
            <IconEye className="h-3 w-3 text-muted-foreground" />
          </Button>
        </DialogTrigger>

        <DialogContent className="max-w-3xl max-h-[80vh]">
          {previewTemplate ? (
            // Preview view
            <PreviewView
              template={previewTemplate}
              onBack={handleBackFromPreview}
              onSelect={() => handleSelect(previewTemplate.id)}
            />
          ) : (
            // Selector view
            <>
              <DialogHeader>
                <DialogTitle>Seleccionar Plantilla</DialogTitle>
              </DialogHeader>

              {/* Category filter */}
              <div className="flex gap-1.5 flex-wrap">
                <Button
                  variant={activeCategory === null ? 'default' : 'outline'}
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => setActiveCategory(null)}
                >
                  Todas
                </Button>
                {(Object.entries(CATEGORY_CONFIG) as [CategoryKey, typeof CATEGORY_CONFIG[CategoryKey]][]).map(([key, config]) => {
                  const Icon = config.icon
                  return (
                    <Button
                      key={key}
                      variant={activeCategory === key ? 'default' : 'outline'}
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => setActiveCategory(key)}
                    >
                      <Icon className="h-3 w-3 mr-1" />
                      {config.label}
                    </Button>
                  )
                })}
              </div>

              {/* Templates grid */}
              <ScrollArea className="h-[50vh]">
                <div className="grid grid-cols-3 gap-3 pr-4">
                  {filteredTemplates.map((template) => (
                    <TemplateCard
                      key={template.id}
                      template={template}
                      isSelected={selectedTemplate === template.id}
                      onSelect={() => handleSelect(template.id)}
                      onPreview={() => handlePreview(template)}
                    />
                  ))}
                </div>
              </ScrollArea>

              {/* Info about external templates */}
              <p className="text-xs text-muted-foreground">
                Las plantillas marcadas con <Badge variant="secondary" className="text-[10px] py-0 h-4 mx-1">Slidesgo</Badge>
                son externas. Haz clic en preview para ver más detalles.
              </p>
            </>
          )}
        </DialogContent>
      </Dialog>
    )
  }

  // Full mode - show grid directly (not used in compact panel)
  return (
    <div className="space-y-3">
      {/* Category filter */}
      <div className="flex gap-1 flex-wrap">
        <Button
          variant={activeCategory === null ? 'default' : 'ghost'}
          size="sm"
          className="h-6 text-[10px] px-2"
          onClick={() => setActiveCategory(null)}
        >
          Todas
        </Button>
        {(Object.entries(CATEGORY_CONFIG) as [CategoryKey, typeof CATEGORY_CONFIG[CategoryKey]][]).map(([key, config]) => (
          <Button
            key={key}
            variant={activeCategory === key ? 'default' : 'ghost'}
            size="sm"
            className="h-6 text-[10px] px-2"
            onClick={() => setActiveCategory(key)}
          >
            {config.label}
          </Button>
        ))}
      </div>

      {/* Templates grid */}
      <div className="grid grid-cols-2 gap-2">
        {filteredTemplates.slice(0, 6).map((template) => (
          <TemplateCard
            key={template.id}
            template={template}
            isSelected={selectedTemplate === template.id}
            onSelect={() => handleSelect(template.id)}
            onPreview={() => handlePreview(template)}
          />
        ))}
      </div>

      {filteredTemplates.length > 6 && (
        <Button
          variant="ghost"
          size="sm"
          className="w-full h-7 text-xs"
          onClick={() => setIsDialogOpen(true)}
        >
          Ver todas las plantillas ({filteredTemplates.length})
        </Button>
      )}
    </div>
  )
}

export default TemplateSelector
