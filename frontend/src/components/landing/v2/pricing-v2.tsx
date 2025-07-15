"use client"

import { useState } from "react"
import { motion } from "framer-motion"
import { useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { 
  IconCheck, 
  IconStar, 
  IconShieldCheck, 
  IconHeadphones, 
  IconRefresh,
  IconSparkles
} from "@tabler/icons-react"

const pricingPlans = [
  {
    name: "Básico",
    description: "Perfecto para equipos pequeños",
    monthlyPrice: 0,
    yearlyPrice: 0,
    badge: null,
    features: [
      "Hasta 1,000 documentos",
      "Búsqueda básica",
      "Análisis IA básico",
      "Almacenamiento 10GB",
      "Soporte por email",
      "Integraciones básicas"
    ]
  },
  {
    name: "Profesional",
    description: "Para equipos en crecimiento",
    monthlyPrice: 49,
    yearlyPrice: 399,
    badge: "Más Popular",
    features: [
      "Hasta 10,000 documentos",
      "Búsqueda semántica avanzada",
      "Todos los agentes IA",
      "Almacenamiento 100GB",
      "Análisis avanzado",
      "Firmas digitales incluidas",
      "Integraciones premium",
      "Soporte prioritario"
    ]
  },
  {
    name: "Empresarial",
    description: "Para organizaciones grandes",
    monthlyPrice: 99,
    yearlyPrice: 799,
    badge: null,
    features: [
      "Documentos ilimitados",
      "IA personalizada",
      "Análisis predictivo",
      "Almacenamiento ilimitado",
      "Workflows personalizados",
      "SSO y seguridad avanzada",
      "API completa",
      "Soporte dedicado 24/7",
      "Onboarding personalizado"
    ]
  }
]

const trustFeatures = [
  {
    icon: IconShieldCheck,
    title: "Pagos 100% seguros",
    description: "Encriptación SSL y protección de datos"
  },
  {
    icon: IconHeadphones,
    title: "Soporte dedicado",
    description: "Asistencia especializada cuando lo necesites"
  },
  {
    icon: IconRefresh,
    title: "Actualizaciones regulares",
    description: "Nuevas características sin costo adicional"
  }
]

export function PricingV2() {
  const [isYearly, setIsYearly] = useState(false)
  const router = useRouter()
  const { isSignedIn } = useAuth()

  const handleChoosePlan = (planName: string) => {
    if (planName === "Básico") {
      if (isSignedIn) {
        router.push('/dashboard')
      } else {
        router.push('/auth/sign-up')
      }
    } else {
      router.push('/pricing')
    }
  }

  return (
    <section className="relative px-6 py-24 lg:px-8 bg-gray-50 dark:bg-gray-900">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <motion.div
          className="text-center mb-16"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          viewport={{ once: true }}
        >
          <Badge variant="secondary" className="mb-4 px-4 py-2">
            <IconSparkles className="mr-2 h-4 w-4" />
            Planes y Precios
          </Badge>
          <h2 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-4xl lg:text-5xl">
            Elige el plan perfecto para tu{' '}
            <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              organización
            </span>
          </h2>
          <p className="mt-4 text-lg text-gray-600 dark:text-gray-300 max-w-2xl mx-auto">
            Desde startups hasta empresas, tenemos el plan ideal para potenciar tu gestión documental con IA.
          </p>
        </motion.div>

        {/* Billing Toggle */}
        <motion.div
          className="flex items-center justify-center mb-12"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          viewport={{ once: true }}
        >
          <div className="flex items-center space-x-4">
            <span className={`text-sm font-medium ${!isYearly ? 'text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400'}`}>
              Mensual
            </span>
            <Switch
              checked={isYearly}
              onCheckedChange={setIsYearly}
              className="data-[state=checked]:bg-blue-600"
            />
            <span className={`text-sm font-medium ${isYearly ? 'text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400'}`}>
              Anual
            </span>
            <Badge variant="secondary" className="ml-2">
              Ahorra 20%
            </Badge>
          </div>
        </motion.div>

        {/* Pricing Cards */}
        <motion.div
          className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-16"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2 }}
          viewport={{ once: true }}
        >
          {pricingPlans.map((plan, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 * index }}
              viewport={{ once: true }}
              className={`relative ${plan.badge ? 'scale-105' : ''}`}
            >
              <Card className={`h-full border-0 shadow-lg hover:shadow-xl transition-shadow duration-300 ${
                plan.badge ? 'ring-2 ring-blue-500 dark:ring-blue-400' : ''
              }`}>
                {plan.badge && (
                  <div className="absolute -top-4 left-1/2 transform -translate-x-1/2">
                    <Badge className="bg-gradient-to-r from-blue-600 to-purple-600 text-white px-4 py-1">
                      <IconStar className="mr-1 h-3 w-3" />
                      {plan.badge}
                    </Badge>
                  </div>
                )}
                
                <CardHeader className="text-center pb-4">
                  <CardTitle className="text-2xl font-bold text-gray-900 dark:text-white">
                    {plan.name}
                  </CardTitle>
                  <p className="text-gray-600 dark:text-gray-300">
                    {plan.description}
                  </p>
                  <div className="mt-4">
                    <div className="flex items-center justify-center space-x-1">
                      <span className="text-4xl font-bold text-gray-900 dark:text-white">
                        ${isYearly ? plan.yearlyPrice : plan.monthlyPrice}
                      </span>
                      <span className="text-gray-600 dark:text-gray-300">
                        /{isYearly ? 'año' : 'mes'}
                      </span>
                    </div>
                    {isYearly && plan.monthlyPrice > 0 && (
                      <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        ${Math.round(plan.yearlyPrice / 12)}/mes facturado anualmente
                      </div>
                    )}
                  </div>
                </CardHeader>

                <CardContent className="pt-0">
                  <ul className="space-y-3 mb-8">
                    {plan.features.map((feature, featureIndex) => (
                      <li key={featureIndex} className="flex items-start space-x-3">
                        <IconCheck className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                        <span className="text-gray-600 dark:text-gray-300">{feature}</span>
                      </li>
                    ))}
                  </ul>

                  <Button
                    className={`w-full ${
                      plan.badge
                        ? 'bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white'
                        : 'bg-gray-900 hover:bg-gray-800 text-white dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100'
                    }`}
                    onClick={() => handleChoosePlan(plan.name)}
                  >
                    {plan.name === "Básico" ? "Comenzar Gratis" : "Elegir Plan"}
                  </Button>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>

        {/* Trust Features */}
        <motion.div
          className="grid grid-cols-1 md:grid-cols-3 gap-8 text-center"
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.3 }}
          viewport={{ once: true }}
        >
          {trustFeatures.map((feature, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 * index }}
              viewport={{ once: true }}
              className="flex flex-col items-center space-y-3"
            >
              <div className="p-3 bg-gradient-to-br from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20 rounded-lg">
                <feature.icon className="h-8 w-8 text-blue-600 dark:text-blue-400" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {feature.title}
              </h3>
              <p className="text-gray-600 dark:text-gray-300">
                {feature.description}
              </p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  )
}