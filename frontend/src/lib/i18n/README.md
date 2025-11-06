# Sistema de Traducciones i18n

## Estructura

```
src/lib/i18n/
├── locales/           # Archivos JSON con traducciones
│   ├── en.json       # Inglés (idioma base)
│   ├── es.json       # Español
│   └── fr.json       # Francés
├── types.ts          # Tipos TypeScript
├── index.ts          # Punto de entrada principal
├── hooks.ts          # Hooks de utilidad
└── README.md         # Esta documentación
```

## Uso Básico

### En componentes

```typescript
import { useTranslation } from '@/lib/i18n/hooks'

export function MyComponent() {
  const { t } = useTranslation()
  
  return (
    <div>
      <h1>{t('dashboard.title')}</h1>
      <button>{t('common.save')}</button>
    </div>
  )
}
```

### Con interpolación de variables

```typescript
// En el JSON:
// "welcome": "Welcome, {name}!"

const { t } = useTranslation()
const message = t('welcome', { name: 'John' }) // "Welcome, John!"
```

### Cambiar idioma

```typescript
const { language, setLanguage, availableLanguages } = useTranslation()

// Cambiar idioma
setLanguage('es')

// Listar idiomas disponibles
availableLanguages.map(lang => (
  <option key={lang.code} value={lang.code}>
    {lang.nativeName}
  </option>
))
```

## Añadir nuevas traducciones

1. **Añadir clave en todos los archivos JSON**:
   ```json
   // en.json
   {
     "mySection": {
       "myKey": "My translation"
     }
   }
   
   // es.json
   {
     "mySection": {
       "myKey": "Mi traducción"
     }
   }
   
   // fr.json
   {
     "mySection": {
       "myKey": "Ma traduction"
     }
   }
   ```

2. **Usar en el componente**:
   ```typescript
   const { t } = useTranslation()
   return <p>{t('mySection.myKey')}</p>
   ```

## Añadir nuevo idioma

1. **Crear archivo de traducción**:
   ```bash
   touch src/lib/i18n/locales/de.json
   ```

2. **Copiar estructura de `en.json`** y traducir

3. **Actualizar tipos en `types.ts`**:
   ```typescript
   export type Language = 'en' | 'es' | 'fr' | 'de'
   
   export const availableLanguages: LanguageOption[] = [
     // ... idiomas existentes
     { code: 'de', name: 'German', nativeName: 'Deutsch' },
   ]
   ```

4. **Actualizar imports en `index.ts`**:
   ```typescript
   import deTranslations from './locales/de.json'
   
   export const staticTranslations = {
     // ... otros idiomas
     de: deTranslations,
   }
   ```

## Convenciones

- **Claves en inglés**: Las claves siempre en inglés y descriptivas
- **Estructura plana cuando sea posible**: Evitar anidación excesiva
- **Agrupación lógica**: Agrupar por sección/página
- **Consistencia**: Usar las mismas claves para conceptos similares

## Type Safety

El sistema proporciona autocompletado de TypeScript para las claves de traducción basándose en el archivo `en.json`.

```typescript
// ✅ TypeScript detectará si la clave existe
t('dashboard.title')

// ❌ TypeScript mostrará error si la clave no existe
t('dashboard.nonExistentKey')
```

## Detección automática de idioma

El sistema detecta automáticamente el idioma del navegador:
- Primero busca en `localStorage`
- Si no hay preferencia guardada, usa `navigator.language`
- Mapea códigos de idioma a los disponibles (es-MX → es)
- Fallback a inglés si no hay coincidencia