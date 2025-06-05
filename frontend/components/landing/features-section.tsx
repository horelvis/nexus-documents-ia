"use client"

import { IconCloudUpload, IconSearch, IconBrain, IconUsers, IconShield, IconMap } from "@tabler/icons-react"

const features = [
  {
    name: 'Subida Inteligente',
    description: 'Arrastra y suelta documentos de cualquier formato. Extraemos automáticamente metadatos y contenido.',
    icon: IconCloudUpload,
    color: 'indigo'
  },
  {
    name: 'Búsqueda Avanzada',
    description: 'Busca por contenido, no solo por nombres. Nuestra IA entiende el contexto de tus consultas.',
    icon: IconSearch,
    color: 'blue'
  },
  {
    name: 'Análisis con IA',
    description: 'Genera resúmenes automáticos, extrae insights clave y clasifica documentos inteligentemente.',
    icon: IconBrain,
    color: 'purple'
  },
  {
    name: 'Colaboración',
    description: 'Comparte documentos de forma segura con tu equipo. Control granular de permisos.',
    icon: IconUsers,
    color: 'green'
  },
  {
    name: 'Seguridad Empresarial',
    description: 'Encriptación end-to-end, auditoría completa y cumplimiento con estándares internacionales.',
    icon: IconShield,
    color: 'red'
  },
  {
    name: 'Rendimiento Optimizado',
    description: 'Búsquedas instantáneas en millones de documentos. Arquitectura escalable y eficiente.',
    icon: IconMap,
    color: 'yellow'
  }
]

const colorClasses = {
  indigo: 'bg-indigo-50 text-indigo-600',
  blue: 'bg-blue-50 text-blue-600', 
  purple: 'bg-purple-50 text-purple-600',
  green: 'bg-green-50 text-green-600',
  red: 'bg-red-50 text-red-600',
  yellow: 'bg-yellow-50 text-yellow-600'
}

export function FeaturesSection() {
  return (
    <section id="features" className="py-24 bg-white sm:py-32">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-base font-semibold leading-7 text-indigo-600">
            Potenciado por IA
          </h2>
          <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
            Todo lo que necesitas para gestionar documentos
          </p>
          <p className="mt-6 text-lg leading-8 text-gray-600">
            Desde la subida hasta el análisis avanzado, Nexus te proporciona todas las herramientas 
            para maximizar el valor de tus documentos.
          </p>
        </div>
        
        <div className="mx-auto mt-16 max-w-2xl sm:mt-20 lg:mt-24 lg:max-w-none">
          <dl className="grid max-w-xl grid-cols-1 gap-x-8 gap-y-16 lg:max-w-none lg:grid-cols-3">
            {features.map((feature) => (
              <div key={feature.name} className="flex flex-col">
                <dt className="text-base font-semibold leading-7 text-gray-900">
                  <div className={`mb-6 flex h-10 w-10 items-center justify-center rounded-lg ${colorClasses[feature.color as keyof typeof colorClasses]}`}>
                    <feature.icon className="h-6 w-6" aria-hidden="true" />
                  </div>
                  {feature.name}
                </dt>
                <dd className="mt-1 flex flex-auto flex-col text-base leading-7 text-gray-600">
                  <p className="flex-auto">{feature.description}</p>
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  )
}