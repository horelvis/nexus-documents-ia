"""
Authentication Provider Implementations.

Available providers:
- ClerkAuthProvider: Clerk.dev for SaaS mode
- OIDCAuthProvider: OpenID Connect for enterprise SSO (KeyCloak, Azure AD, Okta)
- SAMLAuthProvider: SAML 2.0 for enterprise SSO (ADFS, Okta)
- LDAPAuthProvider: Direct LDAP/Active Directory

Usage:
    from app.core.auth.providers import OIDCAuthProvider

    provider = OIDCAuthProvider(config)
    await provider.initialize()
    identity = await provider.verify_token(token)
"""

# Providers are imported dynamically by the factory to avoid
# import errors when optional dependencies are not installed
