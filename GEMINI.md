# Nexus Documents IA - GEMINI Context

This document serves as the primary context and instruction set for GEMINI sessions working on the **Nexus Documents IA** project.

## 1. Project Overview

**Nexus Documents IA (NexusDocs360)** is a comprehensive SaaS platform for intelligent document management, powered by advanced AI. It transforms how organizations interact with documents through features like semantic search, automated entity extraction, AI assistants (Emma), and digital signatures.

*   **Core Value:** Automating document workflows, extraction, and analysis using AI (80% automation target).
*   **Target Audience:** Enterprises requiring robust document handling (Legal, Financial, HR, etc.).
*   **Key Features:**
    *   **Emma AI Assistant:** RAG-based assistant using Elysia Framework, Weaviate, and Ollama.
    *   **Intelligent Workflows:** Powered by Temporalio for durable, long-running processes.
    *   **Hybrid Search:** Combining Elasticsearch (keyword) and Weaviate (semantic).
    *   **Digital Signatures:** Integration with major providers.
    *   **Multi-Tenancy:** Strict data isolation per tenant.

## 2. Technology Stack

### Frontend (`/frontend`)
*   **Framework:** Next.js 15.5.2 (App Router).
*   **Language:** TypeScript.
*   **Styling:** Tailwind CSS, Shadcn UI.
*   **State/Data:** SWR (recently migrated from Context), Zustand.
*   **Auth:** Clerk (OAuth2/JWT).
*   **Build Tool:** `npm`.

### Backend (`/backend`)
*   **Framework:** FastAPI (Python 3.9+).
*   **Database:** PostgreSQL 15 (Async SQLAlchemy).
*   **Vector DB:** Weaviate.
*   **Search:** Elasticsearch.
*   **Queue:** Redis / Celery (and Temporalio for workflows).
*   **Infrastructure:** Docker, Google Cloud Platform (Cloud Run, Cloud SQL).
*   **Microservices:**
    *   `weaviate-service`: Vector search + integrated CAG/agents.
    *   `langextract-service`: Entity Extraction.
    *   `temporalio-service`: Workflow orchestration.
    *   `gotenberg-service`: PDF conversion.

## 3. Architecture Highlights

*   **Modular Monolith / Microservices Hybrid:** The core API (`backend/app`) handles business logic, while specialized tasks (AI extraction, PDF conversion) are offloaded to microservices.
*   **Agent System:** Defined in `AGENTS.md`. Uses a "Chain of Thought" approach for transparency.
*   **State Management (Frontend):** transitioned from "Provider Hell" to a 3-pillar architecture:
    1.  **SWR:** Server state (fetching, caching, revalidation).
    2.  **Zustand:** Global UI state (sidebar, modals).
    3.  **URL State:** Search params for bookmarkable state.

## 4. Development Conventions & Patterns

*   **Async First:** Both Backend (Python `async def`) and Frontend data fetching.
*   **Dependency Injection:** Use FastAPI `Depends` for services (e.g., `get_document_service`). Avoid instantiating services directly in routes.
*   **Type Safety:** Strict Pydantic models in Backend; TypeScript interfaces in Frontend.
*   **"Sign Up First" Flow:** Users register immediately and select plans during onboarding (`/onboarding-simple`).
*   **Token Readiness:** In Frontend, ensure Clerk token is ready (`isTokenReady`) before SWR fetches to avoid 401 errors.

## 5. Key Commands

| Context | Command | Description |
| :--- | :--- | :--- |
| **Frontend** | `npm run dev` | Start dev server (Port 3000) |
| **Frontend** | `npm run build` | Production build |
| **Backend** | `./start-dev.sh` | Start backend services (Docker) |
| **Backend** | `uvicorn app.main:app --reload` | Run FastAPI locally |
| **DB** | `alembic upgrade head` | Run migrations |
| **Testing** | `pytest` | Run backend tests |

## 6. Recent Critical Changes (Memory)

*   **Onboarding Refinement (2025-11-20):**
    *   **Sign Up Enforcement:** `SignUpPage` now redirects users to `/pricing` if no `plan` parameter is present (and not joining via invitation).
    *   **Plan Persistence:** The selected plan is now passed to Clerk's `unsafeMetadata` during sign-up.
    *   **Auto-Selection:** `SimpleOnboardingPage` now reads the plan from `unsafeMetadata` and automatically applies it, skipping the manual selection step if the data exists.
    *   **UserContext:** Updated `syncUserWithBackend` to prioritize `unsafeMetadata` for fetching the selected plan.
*   **Auth Fix:** Implemented `isTokenReady` in `UserContext` to prevent race conditions causing 401s on redirect.
*   **Backend Refactor:** `backend/app/api/v1/documents.py` now uses `get_document_service` dependency injection. Agent logic moved to `AsyncDocumentService`.
*   **Build Status:** Frontend builds successfully (`npm run build`), though with some icon import warnings.

## 7. Directory Structure

*   `backend/`: Core API and microservices.
*   `frontend/`: Next.js application.
*   `deployment/`: IaC and deployment scripts (GCP).
*   `scripts/`: Utility scripts for setup and maintenance.
*   `nginx/`: Proxy configuration.

## 8. Usage Guide for AI Agents

When working in this environment:
1.  **Context is King:** Always check `GEMINI.md` (this file) and `README.md` before making major architectural decisions.
2.  **Respect the Stack:** Do not suggest libraries incompatible with Next.js 15 or the current Python async setup.
3.  **Safety First:** Use `run_shell_command` cautiously. Explain modifications before applying them.
4.  **Preserve Memory:** If a significant change is made (e.g., a new microservice or auth flow change), update the "Recent Critical Changes" section here or use the `save_memory` tool.
