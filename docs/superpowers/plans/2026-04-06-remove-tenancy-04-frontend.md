# Remove Multi-Tenancy — Plan 4: Frontend Refactor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every reference to `tenant_id` / `tenantId` / `X-Tenant-ID` from the Next.js frontend. Delete the tenant service, document-sharing service, and any context that exposes the tenant id. Add a roles multi-select widget to the document upload form and to the connector creation/edit form. Add role badges to document cards. After this plan, the frontend compiles, lints, and renders without sending any tenant header — but the system is **still not runnable end-to-end** because the diagnostics endpoint (Plan 5) still hardcodes a default tenant.

**Architecture:** This plan operates on `frontend/src/`. It depends on Plan 2's API surface (the backend now exposes `roles` and `default_document_roles` fields and rejects `X-Tenant-ID` headers as unknown) and Plan 3's microservices (which now expect `X-User-Roles` and `X-User-Id`). The frontend reads the user's roles from the JWT validated by the existing OIDC client and propagates them per-request via the central API client.

**Tech Stack:** Next.js 15.5 / React 19 / TypeScript / Tailwind / shadcn/ui / next-auth or oidc-client-ts (existing). No new dependencies introduced unless a multi-select component must be added.

**Spec reference:** `docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md` (Section 2.E "Frontend (`frontend/src/`)")
**Previous plan:** `docs/superpowers/plans/2026-04-06-remove-tenancy-03-microservices.md`

**Plan boundaries:**
- ✅ Covers Commit 6 of Section 3.A of the spec.
- ✅ Outputs: every `.ts/.tsx` file under `frontend/src/` either deleted or refactored to drop tenant; new roles widgets added to upload + connector forms; role badges in document cards.
- ❌ Does NOT touch the backend, microservices, tests beyond frontend unit tests, or docs (Plan 5).
- ❌ Does NOT execute the database rebuild (Plan 5).

---

## Volume estimate (from grep against current codebase)

- 85 files under `frontend/src/` contain `tenant_id` or `tenantId` references
- 3 service files are pure tenant artifacts (deleted entirely):
  - `frontend/src/lib/services/tenant.service.ts`
  - `frontend/src/lib/services/document-share.service.ts`
  - `frontend/src/lib/services/shared-documents.service.ts`
- 2 component files are pure sharing artifacts (deleted entirely):
  - `frontend/src/components/documents/share-document-dialog.tsx`
  - `frontend/src/components/documents/share-with-guest-dialog.tsx`
- 5 contexts contain tenant references (modified):
  - `auth-context.tsx`, `user-context.tsx`, `virtual-assistant-context.tsx`, `document-events-context.tsx`, `site-guest-context.tsx`
- 3 type files contain tenant fields (modified):
  - `lib/types/emma.ts` (3 interfaces — find with `grep -n tenant_id frontend/src/lib/types/emma.ts`)
  - `lib/types/index.ts`
  - `lib/types/teams.ts` (likely deleted entirely with the teams concept)

---

## File map (locked decisions)

**Service files DELETED entirely:**
- `frontend/src/lib/services/tenant.service.ts`
- `frontend/src/lib/services/document-share.service.ts`
- `frontend/src/lib/services/shared-documents.service.ts`

**Component files DELETED entirely:**
- `frontend/src/components/documents/share-document-dialog.tsx`
- `frontend/src/components/documents/share-with-guest-dialog.tsx`
- Any `roles-management/*.tsx` if a "manage local roles" UI exists (KeyCloak handles this now)
- Any `team-invitations/*.tsx` if present

**Type files DELETED:**
- `frontend/src/lib/types/teams.ts` (the teams concept is gone)

**Type files MODIFIED:**
- `frontend/src/lib/types/emma.ts` — drop `tenant_id` field from the 3 interfaces that declare it (find with `grep -n tenant_id frontend/src/lib/types/emma.ts`)
- `frontend/src/lib/types/index.ts` — drop `tenant_id` from any exported type
- `frontend/src/lib/types/conversation.ts` — verify and drop if present

**Contexts MODIFIED:**
- `frontend/src/contexts/auth-context.tsx` — replace `tenantId` with `roles: string[]` from JWT
- `frontend/src/contexts/user-context.tsx` — drop `tenantId`
- `frontend/src/contexts/virtual-assistant-context.tsx` — drop `tenantId` from emma calls
- `frontend/src/contexts/document-events-context.tsx` — drop `tenantId` from event payloads
- `frontend/src/contexts/site-guest-context.tsx` — drop `tenantId` (the guest concept may also be removed; verify)

**API client MODIFIED:**
- `frontend/src/lib/api/*` (or wherever the central fetch wrapper lives) — drop the `X-Tenant-ID` header injection, add `X-User-Roles` and `X-User-Id` injection from the JWT claims

**New components ADDED:**
- `frontend/src/components/forms/roles-multi-select.tsx` — reusable widget that lists available roles (loaded from a new `/api/v1/roles/available` endpoint or hardcoded from the canonical catalog) and lets the user pick one or more
- `frontend/src/components/documents/document-roles-badges.tsx` — small badge list shown in document cards: `[SALES] [LEGAL]`

**Forms MODIFIED to use the new widgets:**
- The document upload form (find via `grep -rln "uploadDocument\|upload-document" frontend/src/components/documents`)
- The connector create/edit form (find via `grep -rln "createConnector\|connector-form" frontend/src/components/connectors`)

**Pages DELETED:**
- `frontend/src/app/admin/roles/*` (if it exists) — KeyCloak admin UI handles role management

**Pages MODIFIED:**
- `frontend/src/app/documents/*` — drop tenant from any URL/query state
- `frontend/src/app/connectors/*` — show `default_document_roles` field
- `frontend/src/app/admin/dashboard/*` — drop tenant filters

---

## The canonical refactor patterns

### Pattern A — TypeScript interface

```ts
// BEFORE
export interface Document {
  id: string;
  tenant_id: string;
  title: string;
  // ...
}
```

```ts
// AFTER
export interface Document {
  id: string;
  roles: string[];   // e.g. ["SALES", "LEGAL"] or ["EVERYONE"]
  title: string;
  // ...
}
```

### Pattern B — API client header injection

```ts
// BEFORE (lib/api/client.ts)
function buildHeaders(token: string, tenantId: string) {
  return {
    Authorization: `Bearer ${token}`,
    "X-Tenant-ID": tenantId,
    "Content-Type": "application/json",
  };
}
```

```ts
// AFTER
function buildHeaders(token: string, userId: string, roles: string[]) {
  return {
    Authorization: `Bearer ${token}`,
    "X-User-Id": userId,
    "X-User-Roles": roles.join(","),
    "Content-Type": "application/json",
  };
}
```

### Pattern C — Auth context

```tsx
// BEFORE
type AuthState = {
  token: string;
  tenantId: string;
  userId: string;
};
```

```tsx
// AFTER
type AuthState = {
  token: string;
  userId: string;
  roles: string[];   // parsed from JWT realm_access.roles via the existing mapper
};
```

The roles list is already in the JWT (KeyCloak puts them in `realm_access.roles`). The frontend just needs to read them after JWT parse and store them in the context.

### Pattern D — Component using auth context

```tsx
// BEFORE
const { tenantId } = useAuth();
const docs = await documentService.list(tenantId);
```

```tsx
// AFTER
// No need to thread roles through — the API client adds the headers automatically
const docs = await documentService.list();
```

### Pattern E — Form field for roles

```tsx
import { RolesMultiSelect } from "@/components/forms/roles-multi-select";

<form onSubmit={handleSubmit}>
  {/* ... existing fields ... */}
  <RolesMultiSelect
    value={roles}
    onChange={setRoles}
    label="Visible to roles"
    helperText="Leave empty to use EVERYONE (any authenticated user)"
  />
</form>
```

---

## Task 1: Verify Plans 1, 2, 3 are in place

**Files:** none (verification only)

- [ ] **Step 1: Confirm branch and previous commits**

```bash
git status
git log --oneline -7
```

Expected: branch `refactor/remove-multi-tenancy`, recent commits include the Plan 1, 2, and 3 commits.

- [ ] **Step 2: Confirm backend exposes the new fields**

```bash
grep -n "roles" backend/app/schemas/document.py
grep -n "default_document_roles" backend/app/schemas/connector.py
```

Expected: at least one match in each file showing the field exists.

---

## Task 2: Delete the tenant service and the sharing services

**Files:**
- DELETE: `frontend/src/lib/services/tenant.service.ts`
- DELETE: `frontend/src/lib/services/document-share.service.ts`
- DELETE: `frontend/src/lib/services/shared-documents.service.ts`

- [ ] **Step 1: Find every importer**

```bash
grep -rln "tenant\.service\|tenant-service\|TenantService" frontend/src 2>/dev/null
grep -rln "document-share\.service\|document-share-service\|DocumentShareService" frontend/src 2>/dev/null
grep -rln "shared-documents\.service\|shared-documents-service\|SharedDocumentsService" frontend/src 2>/dev/null
```

Save these lists; they tell you which files need their imports cleaned in Task 4.

- [ ] **Step 2: Delete the files**

```bash
git rm frontend/src/lib/services/tenant.service.ts
git rm frontend/src/lib/services/document-share.service.ts
git rm frontend/src/lib/services/shared-documents.service.ts
```

- [ ] **Step 3: Verify**

```bash
test ! -f frontend/src/lib/services/tenant.service.ts && \
test ! -f frontend/src/lib/services/document-share.service.ts && \
test ! -f frontend/src/lib/services/shared-documents.service.ts && \
echo "deletions ok"
```

---

## Task 3: Delete the sharing dialogs and team-invitation components

**Files:**
- DELETE: `frontend/src/components/documents/share-document-dialog.tsx`
- DELETE: `frontend/src/components/documents/share-with-guest-dialog.tsx`
- DELETE: any `frontend/src/components/team-invitations/*` if present
- DELETE: any `frontend/src/app/admin/roles/*` if present

- [ ] **Step 1: Find importers of each dialog**

```bash
grep -rln "share-document-dialog\|ShareDocumentDialog" frontend/src 2>/dev/null
grep -rln "share-with-guest-dialog\|ShareWithGuestDialog" frontend/src 2>/dev/null
```

- [ ] **Step 2: Delete the dialog files**

```bash
git rm frontend/src/components/documents/share-document-dialog.tsx
git rm frontend/src/components/documents/share-with-guest-dialog.tsx
```

- [ ] **Step 3: Look for team-invitation and admin-roles directories**

```bash
ls frontend/src/components/team-invitations 2>/dev/null
ls frontend/src/app/admin/roles 2>/dev/null
```

If either exists, delete it:

```bash
git rm -r frontend/src/components/team-invitations
git rm -r frontend/src/app/admin/roles
```

- [ ] **Step 4: Verify**

```bash
ls frontend/src/components/documents/share-* 2>&1
```

Expected: `No such file or directory` for both share dialogs.

---

## Task 4: Clean up dead imports left by Tasks 2 and 3

**Files:** every file printed in the import-search results from Tasks 2 and 3.

- [ ] **Step 1: Generate the consolidated dead-import list**

```bash
grep -rln "tenant\.service\|TenantService\|document-share\.service\|DocumentShareService\|shared-documents\.service\|SharedDocumentsService\|share-document-dialog\|ShareDocumentDialog\|share-with-guest-dialog\|ShareWithGuestDialog" frontend/src 2>/dev/null > /tmp/dead_imports.txt
wc -l /tmp/dead_imports.txt
```

- [ ] **Step 2: For each file, remove the broken import line and the code that called the import**

Read each file. Remove the `import { ... } from "..."` line for the deleted module. Remove any JSX `<ShareDocumentDialog ... />` usage. If an entire menu item or button only existed to open the deleted dialog, remove that too.

- [ ] **Step 3: Verify zero broken imports**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -20
```

Expected: no errors mentioning the deleted modules or components. Other unrelated errors are acceptable at this stage and will be cleaned up in later tasks.

---

## Task 5: Refactor the type definitions

**Files:**
- `frontend/src/lib/types/emma.ts` (3 interfaces contain `tenant_id` — locate via the grep below)
- `frontend/src/lib/types/index.ts`
- `frontend/src/lib/types/teams.ts` (probably DELETE — verify usage first)
- `frontend/src/lib/types/conversation.ts` (verify)

- [ ] **Step 1: Read `emma.ts` and find each `tenant_id`**

```bash
grep -n "tenant_id" frontend/src/lib/types/emma.ts
```

- [ ] **Step 2: Apply Pattern A**

For each interface containing `tenant_id`, drop the field. Where the type represents a document/object that needs ACL info, add `roles: string[]`.

- [ ] **Step 3: Repeat for `index.ts` and `conversation.ts`**

```bash
grep -n "tenant_id\|tenantId" frontend/src/lib/types/index.ts frontend/src/lib/types/conversation.ts
```

Apply the same transformation.

- [ ] **Step 4: Decide on `teams.ts`**

```bash
grep -rln "from.*types/teams\|from.*\"@/lib/types/teams\"" frontend/src 2>/dev/null
```

If only teams-related (deleted) components imported it, delete the file:

```bash
git rm frontend/src/lib/types/teams.ts
```

If something else imports it, keep the file but drop tenant fields.

- [ ] **Step 5: Add the new types**

In `frontend/src/lib/types/index.ts` (or wherever `Document` is defined):

```ts
export type Role = string;  // e.g. "SALES", "LEGAL", "EVERYONE"
export const EVERYONE_ROLE: Role = "EVERYONE";
```

Add `roles: Role[]` to `Document`. Add `default_document_roles: Role[]` to `Connector`.

- [ ] **Step 6: Verify**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "tenant" | head
```

Expected: no errors about `tenant_id` in type files.

---

## Task 6: Refactor the auth context

**Files:**
- `frontend/src/contexts/auth-context.tsx`

- [ ] **Step 1: Read the file**

- [ ] **Step 2: Apply Pattern C**

Replace the `tenantId` field with `roles: string[]`. The `roles` are extracted from the JWT after login. Keep `userId`. Update the React context type, the provider, and the `useAuth()` hook.

- [ ] **Step 3: Update the JWT parser**

Find where the JWT is parsed (likely a `parseJwt` or `decodeToken` helper). Read `realm_access.roles` from the decoded payload. If the existing OIDC client already extracts them, expose them through the context.

- [ ] **Step 4: Verify**

```bash
grep -n "tenant" frontend/src/contexts/auth-context.tsx
```

Expected: zero matches.

---

## Task 7: Refactor the user context and other contexts

**Files:**
- `frontend/src/contexts/user-context.tsx`
- `frontend/src/contexts/virtual-assistant-context.tsx`
- `frontend/src/contexts/document-events-context.tsx`
- `frontend/src/contexts/site-guest-context.tsx`

- [ ] **Step 1: For each file, drop `tenantId`**

Remove the field from the context type. Remove its initialization. Remove any place it was passed to a service call.

- [ ] **Step 2: Decide on `site-guest-context.tsx`**

The "site guest" feature is part of the deleted document-sharing flow. Check whether anything still uses it:

```bash
grep -rln "useSiteGuest\|SiteGuestProvider" frontend/src 2>/dev/null
```

If only deleted components used it, delete the entire context file. Otherwise, drop tenant from it.

- [ ] **Step 3: Verify**

```bash
grep -n "tenant" frontend/src/contexts/*.tsx
```

Expected: zero matches.

---

## Task 8: Refactor the central API client

**Files:**
- The central fetch wrapper. Find it with:

```bash
grep -rln "X-Tenant-ID" frontend/src/lib 2>/dev/null
```

Typically `frontend/src/lib/api/client.ts` or `frontend/src/lib/api/fetch.ts`.

- [ ] **Step 1: Read the file**

- [ ] **Step 2: Apply Pattern B**

Replace `X-Tenant-ID` injection with `X-User-Id` and `X-User-Roles` injection. Read the user info from the auth context (via a closure or a passed-in argument).

- [ ] **Step 3: Verify**

```bash
grep -n "X-Tenant-ID\|tenantId" frontend/src/lib/api/*.ts 2>/dev/null
```

Expected: zero matches.

---

## Task 9: Refactor the rest of the components and hooks (batched)

**Files:** all 85 files containing `tenant_id`/`tenantId` minus the ones already touched in Tasks 2-8.

- [ ] **Step 1: Generate the working list**

```bash
grep -rln "tenant_id\|tenantId" frontend/src 2>/dev/null > /tmp/frontend_remaining.txt
wc -l /tmp/frontend_remaining.txt
```

- [ ] **Step 2: Apply Pattern D file-by-file**

Most components just consume `tenantId` from the auth context to pass it into a service call. After Task 8, the API client adds the headers automatically, so the prop drilling is redundant. For each file:
- Remove `const { tenantId } = useAuth()` (or equivalent).
- Remove `tenantId` from the service-call argument list.
- If the service signature itself had `tenantId` as a parameter, remove that too.

- [ ] **Step 3: Special-case files that displayed the tenant**

Some UIs may show "Tenant: Acme Corp" in a header or sidebar. Replace with the user's email or remove the chip entirely.

```bash
grep -rln "Tenant:\|TenantName\|tenant_name" frontend/src 2>/dev/null
```

- [ ] **Step 4: Verify the working list shrinks to zero**

```bash
grep -rln "tenant_id\|tenantId" frontend/src 2>/dev/null
```

Expected: zero matches.

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | tail -30
```

Expected: zero errors. If there are errors, fix them before the next task.

---

## Task 10: Build the `RolesMultiSelect` widget

**Files:**
- Create: `frontend/src/components/forms/roles-multi-select.tsx`

- [ ] **Step 1: Decide on the data source**

Three options:
- (A) Hardcode the canonical catalog from the spec (`ADMIN`, `SALES`, `LEGAL`, `HR`, `FINANCE`, `MEDICAL`, plus `EVERYONE`).
- (B) Add a tiny new endpoint `/api/v1/roles/available` in Plan 5 that reads from `role_mapping.yaml`.
- (C) Read the same YAML at build time via a Next.js loader.

**Default decision:** option (A). Hardcoding the starter catalog matches the spec, which describes the catalog as a "starting set". Adding a role at deployment time is a YAML edit on the backend; adding it to the UI is a one-line addition to the constant. Re-evaluate to (B) if deployments diverge.

- [ ] **Step 2: Create the component**

```tsx
"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

export const AVAILABLE_ROLES = [
  "EVERYONE",
  "ADMIN",
  "SALES",
  "LEGAL",
  "HR",
  "FINANCE",
  "MEDICAL",
] as const;

interface Props {
  value: string[];
  onChange: (roles: string[]) => void;
  label?: string;
  helperText?: string;
  disabled?: boolean;
}

export function RolesMultiSelect({ value, onChange, label, helperText, disabled }: Props) {
  const toggle = (role: string) => {
    if (value.includes(role)) {
      onChange(value.filter((r) => r !== role));
    } else {
      onChange([...value, role]);
    }
  };

  return (
    <div className="space-y-2">
      {label && <Label>{label}</Label>}
      <div className="grid grid-cols-2 gap-2">
        {AVAILABLE_ROLES.map((role) => (
          <label key={role} className="flex items-center gap-2">
            <Checkbox
              checked={value.includes(role)}
              onCheckedChange={() => toggle(role)}
              disabled={disabled}
            />
            <span className="text-sm">{role}</span>
          </label>
        ))}
      </div>
      {helperText && <p className="text-xs text-muted-foreground">{helperText}</p>}
    </div>
  );
}
```

- [ ] **Step 3: Add a Storybook story or a quick render test**

Either add to existing Storybook (if present) or write a quick test:

```tsx
// __tests__/roles-multi-select.test.tsx
import { render, screen } from "@testing-library/react";
import { RolesMultiSelect } from "@/components/forms/roles-multi-select";

test("renders all canonical roles", () => {
  render(<RolesMultiSelect value={[]} onChange={() => {}} />);
  expect(screen.getByText("EVERYONE")).toBeInTheDocument();
  expect(screen.getByText("LEGAL")).toBeInTheDocument();
});
```

---

## Task 11: Build the `DocumentRolesBadges` component

**Files:**
- Create: `frontend/src/components/documents/document-roles-badges.tsx`

- [ ] **Step 1: Create the component**

```tsx
import { Badge } from "@/components/ui/badge";

interface Props {
  roles: string[];
  className?: string;
}

export function DocumentRolesBadges({ roles, className }: Props) {
  if (!roles || roles.length === 0) return null;
  return (
    <div className={`flex flex-wrap gap-1 ${className ?? ""}`}>
      {roles.map((role) => (
        <Badge key={role} variant={role === "EVERYONE" ? "secondary" : "default"}>
          {role}
        </Badge>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Find the document card components**

```bash
grep -rln "DocumentCard\|document-card" frontend/src/components/documents 2>/dev/null
```

- [ ] **Step 3: Insert `<DocumentRolesBadges roles={doc.roles} />` into each card**

Place it near the title or in the metadata footer.

---

## Task 12: Wire `RolesMultiSelect` into the upload form

**Files:**
- Find the upload form:

```bash
grep -rln "uploadDocument\|use-upload\|DocumentUploadForm" frontend/src/components/documents frontend/src/contexts 2>/dev/null
```

Likely candidates: `frontend/src/contexts/upload-context.tsx`, a form component near it.

- [ ] **Step 1: Read the form**

- [ ] **Step 2: Add a `roles: string[]` field to the form state**

Default value: `["EVERYONE"]`.

- [ ] **Step 3: Render `<RolesMultiSelect />`**

Place it after the existing fields.

- [ ] **Step 4: Pass `roles` to the upload service call**

The service signature already accepts `roles` (added in Plan 2's schema update).

- [ ] **Step 5: Verify type-check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "upload" | head
```

Expected: zero errors related to the upload form.

---

## Task 13: Wire `RolesMultiSelect` into the connector form

**Files:**
- Find the connector form:

```bash
grep -rln "createConnector\|ConnectorForm\|connector-form" frontend/src/components/connectors frontend/src/app/connectors 2>/dev/null
```

- [ ] **Step 1: Read the form**

- [ ] **Step 2: Add `default_document_roles: string[]` to the form state**

Default value: `["EVERYONE"]`.

- [ ] **Step 3: Render `<RolesMultiSelect />`**

Label it "Default roles for ingested documents". This is admin-only, so the form should already be behind an admin guard.

- [ ] **Step 4: Pass `default_document_roles` to the create/update call**

- [ ] **Step 5: Verify type-check**

---

## Task 14: Update document list/detail views

**Files:**
- `frontend/src/app/documents/page.tsx`
- `frontend/src/app/documents/[id]/page.tsx`
- Anywhere a document is rendered

- [ ] **Step 1: Render `<DocumentRolesBadges />` in the list rows and the detail header**

- [ ] **Step 2: For the detail view, allow editing the roles**

The detail page should have an "Access" section showing the current `roles` and (for users with `ADMIN` role) a button to edit them via `<RolesMultiSelect />`. The save action calls `PATCH /documents/{id}` with the new `roles` array.

- [ ] **Step 3: Verify type-check**

---

## Task 15: Update connector list/detail views

**Files:**
- `frontend/src/app/connectors/page.tsx`
- `frontend/src/app/connectors/[id]/page.tsx`

- [ ] **Step 1: Show `default_document_roles` in the list**

A small badge list per connector row.

- [ ] **Step 2: Show + edit `default_document_roles` in the detail page**

Same `<RolesMultiSelect />` as in the create form.

---

## Task 16: Run the full type-check and lint

**Files:** none (verification only)

- [ ] **Step 1: TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 2: ESLint**

```bash
cd frontend && npm run lint
```

Expected: zero errors. Warnings about unused imports are OK if they're in files that are being deleted in a later sub-task; otherwise fix them.

- [ ] **Step 3: Build**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

Expected: build succeeds. The Next.js standalone output should be created.

---

## Task 17: Run the frontend unit tests

**Files:** none (test execution)

- [ ] **Step 1: Run vitest / jest**

```bash
cd frontend && npm test -- --run 2>&1 | tail -40
```

(Adjust the command for the test runner in use.)

Expected: all tests pass. Failing tests that reference deleted services or `tenantId` props need to be updated to the new shape.

- [ ] **Step 2: Add unit tests for the new widgets**

If not already added in Tasks 10 and 11, add tests for `RolesMultiSelect` (toggle behavior) and `DocumentRolesBadges` (renders all roles, EVERYONE styled differently).

---

## Task 18: Final repo-wide verification

**Files:** none (verification only)

- [ ] **Step 1: Zero `tenant_id`/`tenantId` references**

```bash
grep -rln "tenant_id\|tenantId" frontend/src 2>/dev/null
```

Expected: zero matches.

- [ ] **Step 2: Zero `X-Tenant-ID` references**

```bash
grep -rn "X-Tenant-ID" frontend/src 2>/dev/null
```

Expected: zero matches.

- [ ] **Step 3: Zero references to deleted services**

```bash
grep -rln "tenant\.service\|document-share\.service\|shared-documents\.service\|ShareDocumentDialog" frontend/src 2>/dev/null
```

Expected: zero matches.

- [ ] **Step 4: Build still works**

Re-run Task 16 Step 3.

---

## Task 19: Commit Plan 4

**Files:** none (git operation)

- [ ] **Step 1: Stage all frontend changes**

```bash
git add frontend/src
```

- [ ] **Step 2: Verify the diff**

```bash
git status --short
git diff --stat HEAD | tail -10
```

Expected: ~85+ files modified, ~5 files deleted, ~3 files added (the new widgets).

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
refactor(frontend): drop tenant context, add role selectors

Implements Plan 4 of the multi-tenancy removal refactor.

- Delete tenant.service.ts, document-share.service.ts, and
  shared-documents.service.ts (the underlying backend endpoints were
  removed in Plan 2).
- Delete share-document-dialog.tsx, share-with-guest-dialog.tsx, and
  any team-invitations / admin/roles pages.
- Refactor auth-context.tsx, user-context.tsx, virtual-assistant-context.tsx,
  document-events-context.tsx, site-guest-context.tsx to drop tenantId.
  auth-context now exposes `roles: string[]` parsed from the JWT.
- Refactor the central API client to inject X-User-Id and X-User-Roles
  headers instead of X-Tenant-ID. Headers are read from the auth context.
- Drop tenant_id from lib/types/{emma,index,conversation}.ts. Add roles
  to Document and default_document_roles to Connector.
- Delete lib/types/teams.ts (the teams concept is gone).
- Add RolesMultiSelect (frontend/src/components/forms/) and
  DocumentRolesBadges (frontend/src/components/documents/).
- Wire RolesMultiSelect into the document upload form and the connector
  create/edit form. Default value: ["EVERYONE"].
- Wire DocumentRolesBadges into document cards and the document detail
  view. Detail view allows editing roles for ADMIN users.

The system is still not runnable end-to-end: the diagnostics endpoint
(Plan 5) still hardcodes _DEFAULT_TENANT, and the actual database
rebuild has not been executed yet.

Spec: docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md
Plan: docs/superpowers/plans/2026-04-06-remove-tenancy-04-frontend.md

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify the commit**

```bash
git log -1 --stat | tail -20
```

---

## Task 20: Self-check before handing off to Plan 5

**Files:** none (verification only)

- [ ] **Step 1: Confirm zero tenant references in frontend**

```bash
grep -rln "tenant_id\|tenantId\|X-Tenant-ID\|tenant\.service\|TenantContext" frontend/src 2>/dev/null
```

Expected: zero matches.

- [ ] **Step 2: Confirm `npm run build` succeeds**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: build OK.

- [ ] **Step 3: Confirm Docker frontend image still builds**

```bash
cd backend/docker && COMPOSE_BAKE=false docker compose build --no-cache frontend 2>&1 | tail -20
```

Expected: image builds successfully (the Plan 1 docker-compose changes should still be in place).

- [ ] **Step 4: Mark Plan 4 complete**

Plan 4 is done. The codebase now has:
- A frontend that compiles, builds, and renders without any tenant references.
- A roles widget for upload and connector forms.
- Role badges in document cards and detail views.
- An API client that propagates `X-User-Id` and `X-User-Roles` automatically.

**The application stack is still not runnable end-to-end** because:
- The diagnostics endpoint in `emma-agent-service/app/api/diagnostics.py` still hardcodes `_DEFAULT_TENANT`.
- The running database still has the old schema with `tenant_id` columns.
- Tests in `backend/tests/` and `backend/microservices/*/tests/` may still reference tenant fixtures.
- `CLAUDE.md`, `README.md`, and the `docs/` tree still describe the multi-tenant model.

Plan 5 is the final plan: it rewrites the diagnostics module, updates all remaining tests, executes the drop & rebuild against the running stack, and updates all docs.

Hand off to `docs/superpowers/plans/2026-04-06-remove-tenancy-05-validation-rebuild.md`.
