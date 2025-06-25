# Cypress E2E Tests - Nexus

## Configuración Inicial

Los tests de Cypress ya están configurados. Asegúrate de que:

1. El frontend esté corriendo en `http://localhost:3000`
2. El backend esté corriendo en `http://localhost:8000`
3. La base de datos tenga datos de prueba

## Ejecutar Tests

### Modo Interactivo (Recomendado para desarrollo)
```bash
npm run cypress:open
# o
npm run test:e2e:ui
```

### Modo Headless (CI/CD)
```bash
npm run cypress:run
# o
npm run test:e2e
```

### Ejecutar tests específicos
```bash
# Solo tests de autenticación
npx cypress run --spec "cypress/e2e/auth.cy.ts"

# Solo tests de documentos
npx cypress run --spec "cypress/e2e/documents.cy.ts"
```

## Estructura de Tests

```
cypress/
├── e2e/                    # Tests E2E
│   ├── auth.cy.ts         # Tests de autenticación
│   └── documents.cy.ts    # Tests de documentos
├── fixtures/              # Datos de prueba
│   ├── test-users.json   # Usuarios de prueba
│   └── test-documents.json # Documentos de prueba
├── support/              # Comandos y configuración
│   ├── commands.ts      # Comandos personalizados
│   └── e2e.ts          # Configuración global
└── downloads/           # Archivos descargados durante tests
```

## Comandos Personalizados

### `cy.login(email, password)`
Realiza login con las credenciales proporcionadas
```javascript
cy.login('test@example.com', 'TestPass123!')
```

### `cy.uploadDocument(fileName, tags)`
Sube un documento con etiquetas opcionales
```javascript
cy.uploadDocument('test.pdf', ['importante', 'legal'])
```

### `cy.waitForApi(alias)`
Espera a que una llamada API se complete
```javascript
cy.waitForApi('documents')
```

## Variables de Entorno

Configuradas en `cypress.config.ts`:
- `TEST_USER_EMAIL`: Email de usuario de prueba
- `TEST_USER_PASSWORD`: Contraseña de usuario de prueba
- `API_URL`: URL del backend

## Mejores Prácticas

1. **Usa data-testid**: Para selectores estables
   ```html
   <button data-testid="submit-button">Submit</button>
   ```

2. **Evita selectores frágiles**: No uses clases CSS que puedan cambiar
   ```javascript
   // Malo
   cy.get('.btn-primary-xl-2')
   
   // Bueno
   cy.get('[data-testid="submit-button"]')
   ```

3. **Usa comandos personalizados**: Para acciones repetitivas

4. **Limpia el estado**: Entre tests para evitar dependencias

5. **Usa fixtures**: Para datos de prueba consistentes

## Debugging

- Usa `cy.pause()` para pausar la ejecución
- Usa `cy.debug()` para debugger en consola
- Los screenshots se guardan automáticamente en fallos
- Los videos se graban por defecto

## CI/CD

Para ejecutar en CI/CD:
```yaml
- name: Run E2E tests
  run: |
    npm run build
    npm run start &
    npx wait-on http://localhost:3000
    npm run test:e2e
```