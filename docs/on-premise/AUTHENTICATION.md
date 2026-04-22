# On-Premise Authentication Guide

This guide covers setting up enterprise authentication for NouxCubeIA on-premise deployments using OIDC/SAML providers.

## Supported Identity Providers

| Provider | Protocol | Status |
|----------|----------|--------|
| **KeyCloak** | OIDC/SAML | Full Support |
| **Azure AD / Entra ID** | OIDC/SAML | Full Support |
| **Okta** | OIDC | Full Support |
| **Auth0** | OIDC | Full Support |
| **Google Workspace** | OIDC | Full Support |
| **Active Directory (ADFS)** | SAML 2.0 | Full Support |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     On-Premise Authentication Flow                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────┐     ┌─────────────┐     ┌─────────────┐     ┌────────────┐    │
│  │  User   │────▶│  Frontend   │────▶│   Backend   │────▶│    IdP     │    │
│  │ Browser │     │  Next.js    │     │   FastAPI   │     │ KeyCloak/  │    │
│  └─────────┘     └─────────────┘     └─────────────┘     │ Azure AD   │    │
│       │                                    │              └────────────┘    │
│       │                                    │                    │           │
│       │         ┌──────────────────────────┘                    │           │
│       │         │                                               │           │
│       │         ▼                                               │           │
│       │    ┌─────────────┐                                      │           │
│       │    │  Session    │◀─────────────────────────────────────┘           │
│       │    │  Store      │  JWT validation against IdP JWKS                 │
│       └───▶│  (Redis)    │                                                  │
│            └─────────────┘                                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start: KeyCloak Setup

### 1. Deploy KeyCloak

```yaml
# docker-compose.keycloak.yml
services:
  keycloak:
    image: quay.io/keycloak/keycloak:24.0
    environment:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: admin
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://postgres:5432/keycloak
      KC_DB_USERNAME: keycloak
      KC_DB_PASSWORD: keycloak
    command: start-dev
    ports:
      - "8443:8443"
      - "8080:8080"
```

### 2. Configure KeyCloak Realm

1. Create a new realm: `nexusdocs`
2. Create a client:
   - **Client ID**: `nexusdocs-client`
   - **Client Protocol**: `openid-connect`
   - **Access Type**: `confidential`
   - **Valid Redirect URIs**: `https://your-app.com/api/v1/auth/callback`

3. Create groups for role mapping:
   - `/Administradores` (Administrators → `ADMIN`)
   - `/Comercial` (Sales → `SALES`)
   - `/Departamento Legal` (Legal → `LEGAL`)
   - `/Recursos Humanos` (HR → `HR`)
   - `/Finanzas` (Finance → `FINANCE`)
   - `/Médicos` (Medical → `MEDICAL`)

### 3. Configure NouxCubeIA

```bash
# backend/docker/.env

# Authentication Provider
AUTH_PROVIDER=oidc

# OIDC Configuration
OIDC_ISSUER_URL=https://keycloak.company.com/realms/nexusdocs
OIDC_CLIENT_ID=nexusdocs-client
OIDC_CLIENT_SECRET=your-client-secret-from-keycloak
OIDC_SCOPES=openid,profile,email,groups

# Group to Role Mapping (group paths match role_mapping.yaml)
OIDC_ADMIN_GROUP=/Administradores
OIDC_USER_GROUP=/Comercial

# JIT Provisioning
OIDC_JIT_PROVISIONING=true

# Session Configuration
SESSION_SECRET=your-secure-session-secret-min-32-chars
SESSION_EXPIRE_HOURS=24
```

---

## Azure AD / Entra ID Setup

### 1. Register Application in Azure

1. Go to **Azure Portal** → **Microsoft Entra ID** → **App registrations**
2. Click **New registration**:
   - **Name**: `NouxCubeIA`
   - **Supported account types**: `Accounts in this organizational directory only`
   - **Redirect URI**: `https://your-app.com/api/v1/auth/callback`

3. After creation, note:
   - **Application (client) ID**: Used as `OIDC_CLIENT_ID`
   - **Directory (tenant) ID**: Used in issuer URL

4. Create a **Client Secret**:
   - Go to **Certificates & secrets**
   - Click **New client secret**
   - Copy the **Value** (shown only once)

### 2. Configure API Permissions

Add these permissions:
- `openid` (Delegated)
- `profile` (Delegated)
- `email` (Delegated)
- `User.Read` (Delegated)
- `GroupMember.Read.All` (Delegated) - for group mapping

### 3. Create Security Groups

Create groups in Azure AD mirroring the canonical role names:
- `SG-Administradores` → `ADMIN`
- `SG-Comercial` → `SALES`
- `SG-Departamento-Legal` → `LEGAL`
- `SG-Recursos-Humanos` → `HR`
- `SG-Finanzas` → `FINANCE`
- `SG-Medicos` → `MEDICAL`

### 4. Configure NouxCubeIA

```bash
# backend/docker/.env

AUTH_PROVIDER=oidc

# Azure AD Configuration
OIDC_ISSUER_URL=https://login.microsoftonline.com/{tenant-id}/v2.0
OIDC_CLIENT_ID=your-application-client-id
OIDC_CLIENT_SECRET=your-client-secret
OIDC_SCOPES=openid,profile,email

# Azure AD Group IDs (use Object IDs from Azure)
OIDC_ADMIN_GROUP=12345678-1234-1234-1234-123456789abc
OIDC_USER_GROUP=87654321-4321-4321-4321-cba987654321

OIDC_JIT_PROVISIONING=true
```

---

## Okta Setup

### 1. Create Okta Application

1. Go to **Okta Admin Console** → **Applications** → **Create App Integration**
2. Select:
   - **Sign-in method**: `OIDC - OpenID Connect`
   - **Application type**: `Web Application`

3. Configure:
   - **App integration name**: `NouxCubeIA`
   - **Sign-in redirect URIs**: `https://your-app.com/api/v1/auth/callback`
   - **Sign-out redirect URIs**: `https://your-app.com/logout`

### 2. Configure NouxCubeIA

```bash
# backend/docker/.env

AUTH_PROVIDER=oidc

# Okta Configuration
OIDC_ISSUER_URL=https://your-org.okta.com
OIDC_CLIENT_ID=your-okta-client-id
OIDC_CLIENT_SECRET=your-okta-client-secret
OIDC_SCOPES=openid,profile,email,groups

OIDC_ADMIN_GROUP=/Administradores
OIDC_USER_GROUP=/Comercial
```

---

## Group to Role Mapping

NouxCubeIA maps IdP group paths to canonical application roles:

| IdP Group Path | Canonical Role | Permissions |
|----------------|----------------|-------------|
| `/Administradores` | `ADMIN` | Full access, user management, settings |
| `/Comercial` | `SALES` | Upload, view, edit documents |
| `/Departamento Legal` | `LEGAL` | Upload, view, edit documents |
| `/Recursos Humanos` | `HR` | Upload, view, edit documents |
| `/Finanzas` | `FINANCE` | Upload, view, edit documents |
| `/Médicos` | `MEDICAL` | Upload, view, edit documents |

### Role Mapping Configuration

The group-to-role mapping is defined in `backend/app/config/role_mapping.yaml` (YAML, not Python). The `AuthProvider.map_groups_to_roles()` method reads this file and translates KeyCloak group paths to canonical role identifiers.

Example `role_mapping.yaml`:
```yaml
# KeyCloak group path → canonical role
group_to_role:
  "/Administradores": ADMIN
  "/Comercial": SALES
  "/Departamento Legal": LEGAL
  "/Recursos Humanos": HR
  "/Finanzas": FINANCE
  "/Médicos": MEDICAL
```

To add a new role mapping:
1. Create the KeyCloak group (e.g., `/Nuevo-Departamento`)
2. Add a line to `role_mapping.yaml` mapping it to a canonical role
3. Restart the API service (the YAML is read on startup)
4. Assign users to the group via KeyCloak admin UI

---

## JIT Provisioning (Just-In-Time)

When enabled, users are automatically created on first login:

```
┌─────────────────────────────────────────────────────────────┐
│  JIT PROVISIONING FLOW                                       │
├─────────────────────────────────────────────────────────────┤
│  1. User authenticates with IdP                              │
│  2. Backend receives JWT with user info + groups             │
│  3. Backend checks if user exists:                           │
│     ├── EXISTS → Update groups/roles, create session         │
│     └── NOT EXISTS → Create user + assign tenant + roles     │
│  4. Session created, user redirected to dashboard            │
└─────────────────────────────────────────────────────────────┘
```

### Configuration

```bash
# Enable JIT Provisioning
OIDC_JIT_PROVISIONING=true

# Attribute mapping
OIDC_ATTRIBUTE_EMAIL=email
OIDC_ATTRIBUTE_NAME=name
OIDC_ATTRIBUTE_GROUPS=groups
```

---

## SAML 2.0 Configuration

For ADFS or other SAML providers:

```bash
# backend/docker/.env

AUTH_PROVIDER=saml

# SAML Configuration
SAML_IDP_METADATA_URL=https://adfs.company.com/FederationMetadata/2007-06/FederationMetadata.xml
SAML_SP_ENTITY_ID=https://nexusdocs.company.com
SAML_ACS_URL=https://nexusdocs.company.com/api/v1/auth/saml/acs
SAML_CERTIFICATE_PATH=/app/certs/saml.crt
SAML_PRIVATE_KEY_PATH=/app/certs/saml.key

# Attribute Mapping
SAML_ATTRIBUTE_EMAIL=http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress
SAML_ATTRIBUTE_NAME=http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name
SAML_ATTRIBUTE_GROUPS=http://schemas.xmlsoap.org/claims/Group
```

---

## Session Management

### Redis Session Store

```bash
# Session configuration
SESSION_STORE=redis
REDIS_URL=redis://redis:6379/1
SESSION_EXPIRE_HOURS=24
SESSION_SECURE_COOKIE=true  # Requires HTTPS
```

### Session Security

```bash
# Security settings
SESSION_SECRET=your-secure-secret-at-least-32-characters
SESSION_COOKIE_NAME=nexusdocs_session
SESSION_SAME_SITE=lax  # or strict for enhanced security
SESSION_HTTP_ONLY=true
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| **Redirect URI mismatch** | Ensure callback URL in IdP matches exactly |
| **Groups not received** | Check IdP group claims configuration |
| **Token validation fails** | Verify OIDC_ISSUER_URL is correct |
| **User not created** | Enable JIT provisioning or pre-create users |

### Debug Logging

```bash
# Enable auth debug logging
LOG_LEVEL=DEBUG
AUTH_DEBUG=true
```

### Test OIDC Configuration

```bash
# Verify OIDC discovery
curl https://your-idp.com/.well-known/openid-configuration | jq

# Test token endpoint
curl -X POST https://your-idp.com/protocol/openid-connect/token \
  -d "grant_type=client_credentials" \
  -d "client_id=$OIDC_CLIENT_ID" \
  -d "client_secret=$OIDC_CLIENT_SECRET"
```

---

## Security Best Practices

1. **Use HTTPS**: Always enable TLS for production
2. **Rotate Secrets**: Change client secrets periodically
3. **Limit Scopes**: Request only necessary OAuth scopes
4. **Enable MFA**: Configure MFA at the IdP level
5. **Audit Logs**: Monitor authentication events
6. **Session Timeout**: Set appropriate session expiration

---

## Related Documentation

- [MODULAR_ARCHITECTURE.md](../architecture/MODULAR_ARCHITECTURE.md) - Microservices architecture overview
- [ACL_SYSTEM.md](../architecture/ACL_SYSTEM.md) - Access Control configuration
- [README-ONPREMISE.md](../../README-ONPREMISE.md) - Main on-premise guide
