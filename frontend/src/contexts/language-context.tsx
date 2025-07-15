'use client'

import React, { createContext, useContext, useState, useEffect } from 'react'
import { Language, availableLanguages, staticTranslations, TranslationKey } from '@/lib/i18n'

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  t: (key: TranslationKey) => string
  availableLanguages: typeof availableLanguages
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>('en')
  const [isClient, setIsClient] = useState(false)

  // Detect browser language on mount
  useEffect(() => {
    setIsClient(true)
    
    // Check localStorage first
    const savedLang = localStorage.getItem('preferredLanguage') as Language
    if (savedLang && staticTranslations[savedLang]) {
      setLanguageState(savedLang)
      return
    }

    // Detect browser language
    const browserLang = navigator.language.toLowerCase()
    
    // Map browser language codes to our supported languages
    if (browserLang.startsWith('es')) {
      setLanguageState('es')
    } else if (browserLang.startsWith('fr')) {
      setLanguageState('fr')
    } else {
      setLanguageState('en')
    }
  }, [])

  const setLanguage = (lang: Language) => {
    setLanguageState(lang)
    localStorage.setItem('preferredLanguage', lang)
  }

  const t = (key: TranslationKey | string): string => {
    // Split the key to navigate nested objects
    const keys = key.split('.')
    let value: any = staticTranslations[language]

    for (const k of keys) {
      if (value && typeof value === 'object' && k in value) {
        value = value[k]
      } else {
        // Fallback to English if key not found
        value = staticTranslations['en']
        for (const fallbackKey of keys) {
          if (value && typeof value === 'object' && fallbackKey in value) {
            value = value[fallbackKey]
          } else {
            console.warn(`Translation key not found: ${key}`)
            return key // Return the key itself if not found
          }
        }
        break
      }
    }

    return typeof value === 'string' ? value : key
  }

  // Prevent hydration mismatch by only rendering translation after client mount
  if (!isClient) {
    return (
      <LanguageContext.Provider value={{ 
        language: 'en', 
        setLanguage: () => {}, 
        t: (key) => key,
        availableLanguages 
      }}>
        {children}
      </LanguageContext.Provider>
    )
  }

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t, availableLanguages }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const context = useContext(LanguageContext)
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider')
  }
  return context
}