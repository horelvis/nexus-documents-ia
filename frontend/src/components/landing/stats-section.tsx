"use client"

const stats = [
  { id: 1, name: 'Documentos procesados', value: '50K+' },
  { id: 2, name: 'Tiempo ahorrado promedio', value: '75%' },
  { id: 3, name: 'Precisión en búsquedas', value: '99.2%' },
  { id: 4, name: 'Empresas que confían en nosotros', value: '200+' },
]

export function StatsSection() {
  return (
    <section className="bg-gray-900 py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="mx-auto max-w-2xl lg:max-w-none">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
              Resultados que hablan por sí mismos
            </h2>
            <p className="mt-4 text-lg leading-8 text-gray-300">
              Miles de empresas ya utilizan Nexus para transformar su gestión documental
            </p>
          </div>
          <dl className="mt-16 grid grid-cols-1 gap-0.5 overflow-hidden rounded-2xl text-center sm:grid-cols-2 lg:grid-cols-4">
            {stats.map((stat) => (
              <div key={stat.id} className="flex flex-col bg-white/5 p-8">
                <dt className="text-sm font-semibold leading-6 text-gray-300">{stat.name}</dt>
                <dd className="order-first text-3xl font-bold tracking-tight text-white">{stat.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  )
}