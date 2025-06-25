// Casos de prueba automatizados para Gestión de Documentos - Nexus
// Usando Cypress como framework de testing E2E

describe('Gestión de Documentos', () => {
  beforeEach(() => {
    // Login antes de cada prueba
    cy.login('test@example.com', 'TestPass123!')
    cy.visit('/dashboard/documents')
  })

  describe('TC-DOC-001: Subir documento individual', () => {
    it('debe subir un PDF exitosamente', () => {
      // Click en botón de subir
      cy.get('[data-testid="upload-button"]').click()
      
      // Seleccionar archivo
      cy.get('input[type="file"]').selectFile('cypress/fixtures/test-document.pdf', { force: true })
      
      // Agregar etiquetas
      cy.get('input[placeholder="Agregar etiqueta"]').type('contrato{enter}')
      cy.get('input[placeholder="Agregar etiqueta"]').type('legal{enter}')
      
      // Subir documento
      cy.get('button').contains('Subir').click()
      
      // Verificar notificación de éxito
      cy.contains('Documento subido exitosamente').should('be.visible')
      
      // Verificar que aparece en la lista
      cy.contains('test-document.pdf').should('be.visible')
      
      // Verificar estado de procesamiento
      cy.get('[data-testid="document-status"]').should('contain', 'Procesando')
      
      // Esperar a que se complete el procesamiento (máx 30s)
      cy.get('[data-testid="document-status"]', { timeout: 30000 })
        .should('contain', 'Completado')
    })

    it('debe rechazar archivos no soportados', () => {
      cy.get('[data-testid="upload-button"]').click()
      
      // Intentar subir archivo .exe
      cy.get('input[type="file"]').selectFile('cypress/fixtures/malicious.exe', { force: true })
      
      // Verificar mensaje de error
      cy.contains('Tipo de archivo no soportado').should('be.visible')
      cy.contains('Solo se permiten PDF, DOCX, TXT').should('be.visible')
    })
  })

  describe('TC-DOC-002: Subir múltiples documentos', () => {
    it('debe subir varios documentos a la vez', () => {
      cy.get('[data-testid="upload-button"]').click()
      
      // Seleccionar múltiples archivos
      cy.get('input[type="file"]').selectFile([
        'cypress/fixtures/doc1.pdf',
        'cypress/fixtures/doc2.docx',
        'cypress/fixtures/doc3.txt'
      ], { force: true })
      
      // Verificar preview de archivos
      cy.get('[data-testid="file-preview"]').should('have.length', 3)
      cy.contains('doc1.pdf').should('be.visible')
      cy.contains('doc2.docx').should('be.visible')
      cy.contains('doc3.txt').should('be.visible')
      
      // Subir todos
      cy.get('button').contains('Subir todos').click()
      
      // Verificar progreso individual
      cy.get('[data-testid="upload-progress"]').should('have.length', 3)
      
      // Verificar notificaciones
      cy.contains('3 documentos subidos exitosamente', { timeout: 10000 }).should('be.visible')
    })

    it('debe respetar límite de 10 archivos', () => {
      cy.get('[data-testid="upload-button"]').click()
      
      // Crear array de 11 archivos
      const files = Array.from({ length: 11 }, (_, i) => `cypress/fixtures/file${i + 1}.pdf`)
      
      cy.get('input[type="file"]').selectFile(files, { force: true })
      
      // Verificar mensaje de error
      cy.contains('Máximo 10 archivos permitidos').should('be.visible')
    })
  })

  describe('TC-DOC-003: Ver detalles de documento', () => {
    it('debe mostrar información completa del documento', () => {
      // Click en documento existente
      cy.get('[data-testid="document-item"]').first().click()
      
      // Verificar panel de detalles
      cy.get('[data-testid="document-details"]').should('be.visible')
      
      // Verificar metadatos
      cy.contains('Tamaño:').should('be.visible')
      cy.contains('Fecha de subida:').should('be.visible')
      cy.contains('Tipo:').should('be.visible')
      cy.contains('Estado:').should('be.visible')
      
      // Verificar análisis IA
      cy.get('[data-testid="ai-analysis"]').should('be.visible')
      cy.contains('Resumen:').should('be.visible')
      cy.contains('Etiquetas sugeridas:').should('be.visible')
      
      // Click en ver documento
      cy.get('button').contains('Ver documento').click()
      
      // Verificar que se abre el visor
      cy.get('[data-testid="document-viewer"]').should('be.visible')
    })
  })

  describe('TC-DOC-004: Descargar documento', () => {
    it('debe descargar documento correctamente', () => {
      // Seleccionar documento
      cy.get('[data-testid="document-item"]').first().click()
      
      // Click en descargar
      cy.get('[data-testid="download-button"]').click()
      
      // Verificar que la descarga se inició
      cy.readFile('cypress/downloads/document.pdf').should('exist')
      
      // Verificar notificación
      cy.contains('Descarga iniciada').should('be.visible')
    })
  })

  describe('TC-DOC-005: Eliminar documento', () => {
    it('debe eliminar documento con confirmación', () => {
      // Obtener nombre del documento a eliminar
      cy.get('[data-testid="document-name"]').first().invoke('text').as('docName')
      
      // Seleccionar documento
      cy.get('[data-testid="document-item"]').first().click()
      
      // Click en eliminar
      cy.get('[data-testid="delete-button"]').click()
      
      // Verificar modal de confirmación
      cy.get('[data-testid="confirm-dialog"]').should('be.visible')
      cy.contains('¿Estás seguro de eliminar este documento?').should('be.visible')
      
      // Cancelar primero
      cy.get('button').contains('Cancelar').click()
      cy.get('[data-testid="confirm-dialog"]').should('not.exist')
      
      // Eliminar de nuevo y confirmar
      cy.get('[data-testid="delete-button"]').click()
      cy.get('button').contains('Eliminar').click()
      
      // Verificar notificación
      cy.contains('Documento eliminado').should('be.visible')
      
      // Verificar que no aparece en la lista
      cy.get('@docName').then((name) => {
        cy.contains(name as string).should('not.exist')
      })
    })
  })

  describe('TC-DOC-006: Compartir documento', () => {
    it('debe compartir documento con otro usuario', () => {
      // Seleccionar documento
      cy.get('[data-testid="document-item"]').first().click()
      
      // Click en compartir
      cy.get('[data-testid="share-button"]').click()
      
      // Modal de compartir
      cy.get('[data-testid="share-dialog"]').should('be.visible')
      
      // Ingresar email destinatario
      cy.get('input[placeholder="Email del destinatario"]').type('colleague@example.com')
      
      // Seleccionar permisos
      cy.get('select[name="permissions"]').select('Ver')
      
      // Agregar mensaje opcional
      cy.get('textarea[name="message"]').type('Por favor revisa este documento')
      
      // Enviar invitación
      cy.get('button').contains('Enviar invitación').click()
      
      // Verificar notificación
      cy.contains('Documento compartido exitosamente').should('be.visible')
      
      // Verificar que aparece en la lista de compartidos
      cy.get('[data-testid="shared-with"]').should('contain', 'colleague@example.com')
    })

    it('debe manejar permisos correctamente', () => {
      cy.get('[data-testid="document-item"]').first().click()
      cy.get('[data-testid="share-button"]').click()
      
      // Compartir con permisos de edición
      cy.get('input[placeholder="Email del destinatario"]').type('editor@example.com')
      cy.get('select[name="permissions"]').select('Editar')
      cy.get('button').contains('Enviar invitación').click()
      
      // Verificar íconos de permisos
      cy.get('[data-testid="permission-badge-editor@example.com"]')
        .should('contain', 'Editar')
    })
  })
})

// Helpers para pruebas de documentos
Cypress.Commands.add('uploadDocument', (fileName: string, tags: string[] = []) => {
  cy.get('[data-testid="upload-button"]').click()
  cy.get('input[type="file"]').selectFile(`cypress/fixtures/${fileName}`, { force: true })
  
  tags.forEach(tag => {
    cy.get('input[placeholder="Agregar etiqueta"]').type(`${tag}{enter}`)
  })
  
  cy.get('button').contains('Subir').click()
  cy.contains('Documento subido exitosamente').should('be.visible')
})