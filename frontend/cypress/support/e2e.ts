// ***********************************************************
// This file is processed and loaded automatically before test files.
// You can change the location of this file or turn off processing
// support files with the 'supportFile' config option.
// ***********************************************************

// Import commands.ts using ES2015 syntax:
import './commands'

// Alternatively you can use CommonJS syntax:
// require('./commands')

// Custom types for TypeScript
declare global {
  namespace Cypress {
    interface Chainable {
      /**
       * Custom command to login a user
       * @example cy.login('user@example.com', 'password123')
       */
      login(email: string, password: string): Chainable<void>
      
      /**
       * Custom command to upload a document
       * @example cy.uploadDocument('document.pdf', ['tag1', 'tag2'])
       */
      uploadDocument(fileName: string, tags?: string[]): Chainable<void>
      
      /**
       * Custom command to wait for API response
       * @example cy.waitForApi('documents')
       */
      waitForApi(alias: string): Chainable<void>
    }
  }
}

// Prevent TypeScript from reading file as legacy script
export {}