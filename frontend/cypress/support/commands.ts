// ***********************************************
// Custom commands for Cypress tests
// ***********************************************

// Login command con manejo de sesión
Cypress.Commands.add('login', (email: string, password: string) => {
  cy.session([email, password], () => {
    cy.visit('/sign-in')
    
    // Esperar a que la página cargue
    cy.get('input[name="email"]', { timeout: 10000 }).should('be.visible')
    
    // Llenar credenciales
    cy.get('input[name="email"]').type(email)
    cy.get('input[name="password"]').type(password)
    
    // Submit
    cy.get('button[type="submit"]').contains(/iniciar sesión|sign in/i).click()
    
    // Verificar login exitoso
    cy.url().should('include', '/dashboard')
    
    // Esperar a que se cargue el dashboard
    cy.contains(/dashboard|panel/i, { timeout: 10000 }).should('be.visible')
  })
})

// Upload document command
Cypress.Commands.add('uploadDocument', (fileName: string, tags: string[] = []) => {
  // Click upload button
  cy.get('[data-testid="upload-button"]').click()
  
  // Select file
  cy.get('input[type="file"]').selectFile(`cypress/fixtures/${fileName}`, { force: true })
  
  // Add tags if provided
  tags.forEach(tag => {
    cy.get('input[placeholder*="etiqueta"]').type(`${tag}{enter}`)
  })
  
  // Submit upload
  cy.get('button').contains(/subir|upload/i).click()
  
  // Wait for success notification
  cy.contains(/subido exitosamente|uploaded successfully/i).should('be.visible')
})

// Wait for API response helper
Cypress.Commands.add('waitForApi', (alias: string) => {
  cy.intercept('GET', `**/api/v1/${alias}**`).as(alias)
  cy.wait(`@${alias}`)
})

// Interceptar llamadas API comunes
beforeEach(() => {
  // Interceptar autenticación
  cy.intercept('POST', '**/api/v1/auth/**').as('auth')
  
  // Interceptar documentos
  cy.intercept('GET', '**/api/v1/documents**').as('getDocuments')
  cy.intercept('POST', '**/api/v1/documents**').as('createDocument')
  
  // Interceptar búsquedas
  cy.intercept('GET', '**/api/v1/search**').as('search')
  
  // Interceptar agentes
  cy.intercept('GET', '**/api/v1/agents**').as('getAgents')
})