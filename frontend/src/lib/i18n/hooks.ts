import { useLanguage } from '@/contexts/language-context'
import { TranslationKey } from './types'

/**
 * Hook for translations with interpolation support
 * 
 * Example usage:
 * const { t } = useTranslation()
 * t('welcome.message', { name: 'John' }) // "Welcome, {name}!" -> "Welcome, John!"
 */
export function useTranslation() {
  const { t: translate, language, setLanguage, availableLanguages } = useLanguage()

  const t = (key: TranslationKey | string, params?: Record<string, string | number>) => {
    let text = translate(key)
    
    if (params) {
      Object.entries(params).forEach(([paramKey, value]) => {
        text = text.replace(new RegExp(`\\{${paramKey}\\}`, 'g'), String(value))
      })
    }
    
    return text
  }

  return {
    t,
    language,
    setLanguage,
    availableLanguages,
  }
}