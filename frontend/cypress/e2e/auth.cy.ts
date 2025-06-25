// Casos de prueba automatizados para Autenticación - Nexus
// Usando Cypress como framework de testing E2E

describe('Autenticación y Gestión de Usuarios', () => {
  beforeEach(() => {
    cy.visit('http://localhost:3000')
  })

  describe('TC-AUTH-001: Registro de nuevo usuario', () => {
    it('debe permitir registro exitoso con datos válidos', () => {
      // Generar email único para la prueba
      const uniqueEmail = `test-${Date.now()}@example.com`
      
      cy.visit('/sign-up')
      
      // Llenar formulario de registro
      cy.get('input[name="email"]').type(uniqueEmail)
      cy.get('input[name="password"]').type('SecurePass123!')
      cy.get('input[name="confirmPassword"]').type('SecurePass123!')
      
      // Aceptar términos si existe checkbox
      cy.get('input[type="checkbox"]').check({ force: true })
      
      // Submit
      cy.get('button[type="submit"]').contains('Registrarse').click()
      
      // Verificar redirección a onboarding
      cy.url().should('include', '/onboarding')
      cy.contains('Bienvenido a Nexus').should('be.visible')
    })

    it('debe mostrar errores de validación para datos inválidos', () => {
      cy.visit('/sign-up')
      
      // Email inválido
      cy.get('input[name="email"]').type('invalid-email')
      cy.get('input[name="password"]').type('123') // Contraseña muy corta
      cy.get('input[name="confirmPassword"]').type('456') // No coincide
      
      cy.get('button[type="submit"]').contains('Registrarse').click()
      
      // Verificar mensajes de error
      cy.contains('Email inválido').should('be.visible')
      cy.contains('La contraseña debe tener al menos 8 caracteres').should('be.visible')
      cy.contains('Las contraseñas no coinciden').should('be.visible')
    })
  })

  describe('TC-AUTH-002: Login con credenciales válidas', () => {
    it('debe permitir login exitoso', () => {
      cy.visit('/sign-in')
      
      // Usar credenciales de prueba
      cy.get('input[name="email"]').type('test@example.com')
      cy.get('input[name="password"]').type('TestPass123!')
      
      cy.get('button[type="submit"]').contains('Iniciar sesión').click()
      
      // Verificar redirección al dashboard
      cy.url().should('include', '/dashboard')
      cy.contains('Dashboard').should('be.visible')
      
      // Verificar que el usuario está autenticado
      cy.get('[data-testid="user-menu"]').should('be.visible')
    })
  })

  describe('TC-AUTH-003: Login con credenciales inválidas', () => {
    it('debe mostrar error con credenciales incorrectas', () => {
      cy.visit('/sign-in')
      
      cy.get('input[name="email"]').type('test@example.com')
      cy.get('input[name="password"]').type('WrongPassword123!')
      
      cy.get('button[type="submit"]').contains('Iniciar sesión').click()
      
      // Verificar mensaje de error
      cy.contains('Credenciales inválidas').should('be.visible')
      
      // Verificar que no hay redirección
      cy.url().should('include', '/sign-in')
    })
  })

  describe('TC-AUTH-004: Logout de usuario', () => {
    beforeEach(() => {
      // Login primero
      cy.login('test@example.com', 'TestPass123!')
    })

    it('debe cerrar sesión correctamente', () => {
      // Click en menú de usuario
      cy.get('[data-testid="user-menu"]').click()
      
      // Click en cerrar sesión
      cy.get('[data-testid="logout-button"]').click()
      
      // Confirmar en modal si aparece
      cy.get('button').contains('Confirmar').click({ force: true })
      
      // Verificar redirección a login
      cy.url().should('include', '/sign-in')
      
      // Verificar que no puede acceder a rutas protegidas
      cy.visit('/dashboard')
      cy.url().should('include', '/sign-in')
    })
  })

  describe('TC-AUTH-005: Recuperación de contraseña', () => {
    it('debe enviar email de recuperación', () => {
      cy.visit('/sign-in')
      
      // Click en olvidé mi contraseña
      cy.contains('¿Olvidaste tu contraseña?').click()
      
      // Verificar redirección
      cy.url().should('include', '/forgot-password')
      
      // Ingresar email
      cy.get('input[name="email"]').type('test@example.com')
      cy.get('button[type="submit"]').contains('Enviar').click()
      
      // Verificar mensaje de éxito
      cy.contains('Email enviado').should('be.visible')
      cy.contains('Revisa tu bandeja de entrada').should('be.visible')
    })
  })
})

// Comando personalizado para login rápido en otras pruebas
Cypress.Commands.add('login', (email: string, password: string) => {
  cy.session([email, password], () => {
    cy.visit('/sign-in')
    cy.get('input[name="email"]').type(email)
    cy.get('input[name="password"]').type(password)
    cy.get('button[type="submit"]').contains('Iniciar sesión').click()
    cy.url().should('include', '/dashboard')
  })
})