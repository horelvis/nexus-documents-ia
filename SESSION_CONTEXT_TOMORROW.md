# Session Context: 2025-11-20

## Status
- **Resolved:**
    - Fixed 500 Internal Server Error in `POST /api/v1/engine-templates/from-document` (UUID serialization issue).
    - Improved UI error handling in `DocumentsPage` to separate template creation success from Google Docs opening failure.
- **In Progress:**
    - Investigating why Google Drive tokens are not being saved/found for user `cd8bb336-5653-43fa-b84e-ee1627540d5a`, even though the user reports connecting successfully.
    - The script `check_google_token.py` failed to run locally due to environment issues; needs to be run inside the Docker container.

## Next Steps
1. **Verify Google Drive Token:**
   - Execute the database check *inside* the `api` container to confirm if the token exists for the user.
   - **Suggested Command:**
     ```bash
     docker compose -f backend/docker/docker-compose.yml exec api python3 -c "from app.db.session import SessionLocal; from app.db.models import GoogleDriveToken; from uuid import UUID; db = SessionLocal(); token = db.query(GoogleDriveToken).filter(GoogleDriveToken.user_id == UUID('cd8bb336-5653-43fa-b84e-ee1627540d5a')).first(); print(f'Token found: {token is not None}')"
     ```

2. **Debug OAuth Flow:**
   - If no token is found, trace the `oauth_callback` in `backend/app/api/v1/google_drive.py`.
   - Check logs for "Failed to store Google Drive tokens" or other errors during the callback.

## Key Files
- `backend/app/api/v1/engine_templates.py` (Backend fix)
- `frontend/src/app/(main)/[tenantId]/documents/page.tsx` (Frontend fix)
- `backend/app/api/v1/google_drive.py` (OAuth logic)