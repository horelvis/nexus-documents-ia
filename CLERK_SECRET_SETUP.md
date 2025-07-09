# Setting up Clerk Publishable Key for GitHub Actions

The deployment is failing because the Clerk publishable key is not set in GitHub secrets.

## Quick Setup

1. Go to: https://github.com/horelvis/nexus-documents-ia/settings/secrets/actions

2. Click "New repository secret"

3. Add the following secret:
   - **Name:** `CLERK_PUBLISHABLE_KEY_PRE`
   - **Value:** `pk_test_ZGVlcC1yYWJiaXQtMjkuY2xlcmsuYWNjb3VudHMuZGV2JA`

4. After adding the secret, the deployment will work on the next push.

## Alternative: Use GitHub CLI

If you have GitHub CLI installed:

```bash
gh secret set CLERK_PUBLISHABLE_KEY_PRE \
  --repo horelvis/nexus-documents-ia \
  --body "pk_test_ZGVlcC1yYWJiaXQtMjkuY2xlcmsuYWNjb3VudHMuZGV2JA"
```

## Trigger Deployment

After adding the secret, push any small change to trigger a new deployment:

```bash
git commit --allow-empty -m "Trigger deployment after adding Clerk secret"
git push origin pre
```