"""Celery configuration for the background worker."""
from celery import Celery
from celery.schedules import crontab

from worker_app.core.config import settings

celery_app = Celery(
    "background_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "worker_app.tasks.preview_tasks",
        "worker_app.tasks.email_tasks",
        "worker_app.tasks.indexing_tasks",
        "worker_app.tasks.channel_tasks",
        "worker_app.tasks.connector_tasks",
        "worker_app.tasks.verification_tasks",
    ],
)

celery_app.conf.update(
    task_default_queue="default",
    task_routes={
        "preview.*": {"queue": "preview"},
        "email.*": {"queue": "email"},
        "indexing.*": {"queue": "indexing"},
        "channels.*": {"queue": "channels"},
        "connectors.*": {"queue": "connectors"},
        "verification.*": {"queue": "verification"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    beat_schedule={
        "auto-generate-missing-previews": {
            "task": "preview.auto_generate_missing_previews",
            "schedule": crontab(hour=2, minute=0),
        },
        "cleanup-old-previews": {
            "task": "preview.cleanup_old_previews",
            "schedule": crontab(day_of_month=1, hour=3, minute=0),
        },
        "process-pending-notifications": {
            "task": "email.process_pending_notifications",
            "schedule": crontab(minute="0,30"),
        },
        "auto-retry-failed-indexing": {
            "task": "indexing.auto_retry_failed_indexing",
            "schedule": crontab(minute="0,30"),
        },
        "channels-scheduled-sync": {
            "task": "channels.sync_scheduled",
            "schedule": crontab(minute="*/15"),  # Every 15 minutes
        },
        "connectors-scheduled-sync": {
            "task": "connectors.sync_scheduled",
            "schedule": crontab(minute="*/15"),  # Every 15 minutes
        },
    },
)
