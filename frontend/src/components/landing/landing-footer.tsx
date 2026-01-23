"use client"

import {
  IconFileText,
  IconBrandTwitter,
  IconBrandLinkedin,
  IconBrandGithub,
  IconMail,
  IconPhone,
  IconMapPin,
} from "@tabler/icons-react"

const linkGroups = [
  {
    title: "Producto",
    links: [
      { name: "Características", href: "#features" },
      { name: "Precios", href: "#pricing" },
      { name: "Integraciones", href: "#integrations" },
    ],
  },
  {
    title: "Empresa",
    links: [
      { name: "Sobre Nosotros", href: "#about" },
      { name: "Casos de Éxito", href: "#cases" },
      { name: "Partners", href: "#partners" },
    ],
  },
  {
    title: "Recursos",
    links: [
      { name: "Blog", href: "#blog" },
      { name: "Documentación", href: "#docs" },
      { name: "Centro de Ayuda", href: "#help" },
    ],
  },
  {
    title: "Legal",
    links: [
      { name: "Privacidad", href: "#privacy" },
      { name: "Términos", href: "#terms" },
      { name: "Cookies", href: "#cookies" },
    ],
  },
]

const contactInfo = [
  {
    label: "Escríbenos",
    value: "contacto@nouxcubeia.com",
    href: "mailto:contacto@nouxcubeia.com",
    icon: IconMail,
  },
  {
    label: "Asesor comercial",
    value: "+34 910 123 456",
    href: "tel:+34910123456",
    icon: IconPhone,
  },
  {
    label: "Oficinas",
    value: "Av. Diagonal 640, Barcelona",
    href: "https://maps.google.com/?q=Av.+Diagonal+640,+Barcelona",
    icon: IconMapPin,
  },
]

const social = [
  { name: "Twitter", href: "https://twitter.com/nouxcubeia", icon: IconBrandTwitter },
  { name: "LinkedIn", href: "https://linkedin.com/company/nouxcubeia", icon: IconBrandLinkedin },
  { name: "GitHub", href: "https://github.com/nouxcubeia", icon: IconBrandGithub },
]

export function LandingFooter() {
  const scrollToSection = (href: string) => {
    if (href.startsWith('#')) {
      const element = document.getElementById(href.substring(1))
      element?.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <footer className="relative mt-24 text-gray-300" aria-labelledby="footer-heading">
      <div className="hidden lg:block absolute -translate-x-1/2 rounded-full blur-[10rem] translate-y-1/4 -z-10 left-1/2 top-1/4 w-72 h-60 bg-purple-600/60"></div>
      <div className="relative mx-auto max-w-7xl px-6 pb-10 pt-20 sm:px-8">
        <div className="grid gap-8 rounded-3xl border border-white/10 bg-white/5 p-8 backdrop-blur-xl lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-8">
            <div className="flex items-center">
              <IconFileText className="h-9 w-9 text-[#8b6af6]" />
              <div className="ml-3">
                <p className="text-lg font-semibold text-white">Nexus Documents 360</p>
                <p className="text-sm text-gray-400">Inteligencia documental para asesorías modernas</p>
              </div>
            </div>

            <p className="text-sm leading-6 text-gray-400">
              Centraliza y protege tus documentos estratégicos con flujos de IA, firmas electrónicas y analítica
              operativa en tiempo real. Diseñado para equipos legales, laborales y financieros que necesitan
              velocidad sin renunciar a la seguridad.
            </p>

            <div className="flex flex-wrap items-center gap-3">
              {["ISO 27001 Ready", "Soporte 24/7", "Infraestructura UE"].map((chip) => (
                <span
                  key={chip}
                  className="rounded-full border border-white/15 px-4 py-1 text-xs font-semibold uppercase tracking-wider text-gray-300"
                >
                  {chip}
                </span>
              ))}
            </div>

            <div className="flex items-center gap-4">
              {social.map((item) => (
                <a
                  key={item.name}
                  href={item.href}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-white/5 text-gray-200 transition hover:border-[#8b6af6]/40 hover:text-white"
                >
                  <span className="sr-only">{item.name}</span>
                  <item.icon className="h-5 w-5" aria-hidden="true" />
                </a>
              ))}
            </div>
          </div>

          <div className="space-y-5 rounded-2xl border border-white/10 bg-gray-900/40 p-6">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-gray-400">Contacto directo</p>
            <div className="space-y-5">
              {contactInfo.map((item) => (
                <a
                  key={item.label}
                  href={item.href}
                  className="flex items-start rounded-xl border border-white/5 bg-white/5 p-4 transition hover:border-[#8b6af6]/40 hover:bg-white/10"
                >
                  <item.icon className="mt-1 h-5 w-5 text-[#8b6af6]" aria-hidden="true" />
                  <div className="ml-4">
                    <p className="text-xs uppercase tracking-wide text-gray-400">{item.label}</p>
                    <p className="text-sm font-medium text-white">{item.value}</p>
                  </div>
                </a>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-16 grid gap-8 md:grid-cols-2 lg:grid-cols-4">
          {linkGroups.map((group) => (
            <div key={group.title}>
              <p className="text-sm font-semibold uppercase tracking-wide text-gray-400">{group.title}</p>
              <ul className="mt-5 space-y-3">
                {group.links.map((link) => (
                  <li key={link.name}>
                    <button
                      type="button"
                      onClick={() => scrollToSection(link.href)}
                      className="text-sm text-gray-400 transition hover:text-white"
                    >
                      {link.name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 border-t border-white/10 pt-6 text-xs text-gray-500 sm:flex sm:items-center sm:justify-between">
          <p>&copy; {new Date().getFullYear()} Nexus Documents 360. Todos los derechos reservados.</p>
          <div className="mt-4 flex gap-4 sm:mt-0">
            <button
              type="button"
              onClick={() => scrollToSection('#privacy')}
              className="transition hover:text-white"
            >
              Política de privacidad
            </button>
            <button
              type="button"
              onClick={() => scrollToSection('#terms')}
              className="transition hover:text-white"
            >
              Términos de servicio
            </button>
          </div>
        </div>
      </div>
    </footer>
  )
}
