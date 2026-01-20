// Type definitions for translations
import enTranslations from './locales/en.json'

// Use the English translations as the source of truth for types
export type TranslationKeys = typeof enTranslations

// Helper type to get nested keys with dot notation
type NestedKeyOf<ObjectType extends object> = {
  [Key in keyof ObjectType & (string | number)]: ObjectType[Key] extends object
    ? `${Key}` | `${Key}.${NestedKeyOf<ObjectType[Key]>}`
    : `${Key}`
}[keyof ObjectType & (string | number)]

export type TranslationKey = NestedKeyOf<TranslationKeys>

export type Language = 'en' | 'es' | 'fr'

export interface LanguageOption {
  code: Language
  name: string
  nativeName: string
}

export const availableLanguages: LanguageOption[] = [
  { code: 'en', name: 'English', nativeName: 'English' },
  { code: 'es', name: 'Spanish', nativeName: 'Español' },
  { code: 'fr', name: 'French', nativeName: 'Français' },
]