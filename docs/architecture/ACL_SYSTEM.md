# ACL System — REMOVED (2026-05-04)

> **Status:** This document describes a system that **no longer exists**. It is preserved as historical reference.

## What changed

The role-based access control (ACL) system documented previously was removed across the entire stack on 2026-05-04. After the removal:

- **Authentication** continues to ride on KeyCloak (OIDC/SAML).
- **Authorization** is consolidated onto a single boolean: `User.is_superuser`. Admin and configuration endpoints gate on `Depends(require_superuser)` from `app.core.auth.superuser`.
- **All authenticated users can read every document** in the deployment. There is no per-document, per-role, or per-user filter.
- The `roles` columns on `documents` and `indexed_documents`, the `default_document_roles` column on `connectors`, the Weaviate `roles` property on every collection, and the FalkorDB `user` property on every node and relationship were physically dropped.
- The 8 duplicated `auth_headers.py` helpers no longer carry `EVERYONE_ROLE` / `allowed_roles()`. The `X-User-Roles` HTTP header is no longer consumed by any microservice (it may still be emitted by the main API as informational metadata; downstream services ignore it).
- `UserProfile.roles` survives as informational metadata (displayed in `/auth/me`); it is never consumed for filtering or gating.

## Why

Single-tenant on-premise deployments have no semantic for cross-user document isolation: every user inside the org is meant to see every document. The role-based ACL surface added cost (8 duplicated copies, 12+ filter call sites in Weaviate, 8+ Cypher patterns in FalkorDB, ~270 lines of dead frontend code) without ever being switched on in production. Pre-flight verification confirmed zero documents in any deployment carried a non-`EVERYONE` role tag.

## Spec reference

- `docs/superpowers/specs/2026-05-04-remove-role-based-acl-design.md` — full rationale, alternatives considered, irreversibility decision.
- `docs/superpowers/plans/2026-05-04-remove-role-based-acl-plan.md` — 7-phase implementation plan (PR commit log).

## How to reintroduce role-based ACL (if a future spec needs it)

The migration is destructive: the `roles` columns and indexes were dropped via Alembic `a4b5c6d7e8f9_drop_role_acl_columns.py`. Restoring requires:

1. A pg_dump from before 2026-05-04, taken in the Phase 0 pre-flight (operators were instructed to keep this for ≥30 days post-merge).
2. A new Alembic migration adding the columns back.
3. Reintroducing the `filter_visible_to_user()` and `require_role()` helpers (deleted from `app.core.auth.acl`).
4. Reintroducing the `_roles_filter()` Weaviate helper and the 12 call sites.
5. Re-adding the `user` property to FalkorDB Cypher patterns in `triple_store.py` and `triple_query.py`.

This is a non-trivial undo. Pause and re-verify the requirement before going down this path.
