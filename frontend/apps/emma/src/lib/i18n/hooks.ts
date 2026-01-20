/**
 * i18n Hooks for Emma On-Premise
 *
 * Simplified version without full i18n support.
 * Returns text as-is for now, can be expanded later.
 */

export type TranslationKey = string

/**
 * Hook for translations with interpolation support
 */
export function useTranslation() {
  const t = (key: TranslationKey | string, params?: Record<string, string | number>) => {
    let text = key

    if (params) {
      Object.entries(params).forEach(([paramKey, value]) => {
        text = text.replace(new RegExp(`\\{${paramKey}\\}`, 'g'), String(value))
      })
    }

    return text
  }

  return {
    t,
    language: 'es',
    setLanguage: () => {},
    availableLanguages: ['es', 'en'],
  }
}
