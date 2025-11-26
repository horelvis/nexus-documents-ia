// Main entry point for i18n
import { Language } from './types'

// Dynamic imports for translations
const translations: Record<Language, () => Promise<any>> = {
  en: () => import('./locales/en.json'),
  es: () => import('./locales/es.json'),
  fr: () => import('./locales/fr.json'),
}

// Cache for loaded translations
const translationCache: Partial<Record<Language, any>> = {}

export async function loadTranslations(language: Language) {
  if (translationCache[language]) {
    return translationCache[language]
  }

  try {
    const translationModule = await translations[language]()
    translationCache[language] = translationModule.default || translationModule
    return translationCache[language]
  } catch (error) {
    console.error(`Failed to load translations for ${language}:`, error)
    // Fallback to English if loading fails
    if (language !== 'en') {
      return loadTranslations('en')
    }
    throw error
  }
}

// Synchronous version for initial load (uses pre-imported translations)
import enTranslations from './locales/en.json'
import esTranslations from './locales/es.json'
import frTranslations from './locales/fr.json'

export const staticTranslations = {
  en: enTranslations,
  es: esTranslations,
  fr: frTranslations,
}

export * from './types'