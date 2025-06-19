"""
Unified Worker
Combines all worker functions into a single worker process
"""
from arq import run_worker
from arq.connections import RedisSettings

from app.core.config import settings

# Import all worker modules
from app.workers.categorization_worker import (
    categorize_document,
    categorize_document_batch,
    auto_categorize_pending_documents
)
from app.workers.preview_worker import (
    generate_document_preview,
    generate_preview_batch,
    auto_generate_missing_previews,
    cleanup_old_previews
)
from app.workers.email_worker import (
    send_email,
    send_user_invitation,
    send_team_invitation,
    send_document_share_notification,
    send_password_reset,
    send_bulk_emails,
    process_pending_notifications
)

# Redis settings
redis_settings = RedisSettings(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    database=0,
)

# Combined worker configuration
class WorkerSettings:
    """Settings for unified ARQ worker"""
    redis_settings = redis_settings
    
    # All functions from different workers
    functions = [
        # Categorization functions
        categorize_document,
        categorize_document_batch,
        
        # Preview functions
        generate_document_preview,
        generate_preview_batch,
        
        # Email functions
        send_email,
        send_user_invitation,
        send_team_invitation,
        send_document_share_notification,
        send_password_reset,
        send_bulk_emails,
    ]
    
    # All cron jobs
    cron_jobs = [
        # Run at different times to spread load
        ("*/30 * * * *", process_pending_notifications),  # Every 30 minutes
        ("0 */6 * * *", auto_categorize_pending_documents),  # Every 6 hours
        ("0 2 * * *", auto_generate_missing_previews),  # Daily at 2 AM
        ("0 3 1 * *", cleanup_old_previews),  # Monthly at 3 AM
    ]
    
    # Increased limits for unified worker
    max_jobs = 20
    job_timeout = 600  # 10 minutes