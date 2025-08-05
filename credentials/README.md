# Credentials Directory

This directory contains sensitive credential files that should **NEVER** be committed to version control.

## Files in this directory:

- `github-actions-pre-key.json` - Service account key for GitHub Actions (PRE environment)
- `github-actions-prod-key.json` - Service account key for GitHub Actions (PROD environment)
- `nexus-document-ia-04252dae0146.json` - GCS credentials (if needed locally)
- Any other service account keys or credentials

## Security Notes:

1. **This directory is in .gitignore** - Never remove it from .gitignore
2. **Keep credentials secure** - Only authorized personnel should have access
3. **Rotate regularly** - Service account keys should be rotated periodically
4. **Use Secret Manager** - In production, use Google Secret Manager instead of files
5. **Delete after use** - Remove keys from local machine after adding to GitHub Secrets

## If you accidentally commit credentials:

1. Immediately revoke the compromised keys in GCP Console
2. Generate new keys
3. Update all services using the old keys
4. Remove the file from git history using BFG or git filter-branch

## Best Practices:

- Use separate service accounts for each environment (dev, pre, prod)
- Grant minimal necessary permissions
- Use Workload Identity Federation when possible
- Monitor service account usage in GCP logs