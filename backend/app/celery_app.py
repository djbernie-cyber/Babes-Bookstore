import os
from celery import Celery
from celery.schedules import crontab
from .config import settings

celery_app = Celery(
    "babes_bookstore",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.scrape",
        "app.tasks.verify_licenses",
        "app.tasks.package_bundle",
        "app.tasks.periodic",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=86400,      # 24h hard cap (long catalogue harvests)
    task_soft_time_limit=82800, # 23h soft cap before SIGUSR1
    worker_max_tasks_per_child=50,
    worker_concurrency=4,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        "verify-pending-licenses-daily": {
            "task": "verify.licenses.all",
            "schedule": crontab(hour=3, minute=0),  # 03:00 UTC daily
        },
        "cleanup-expired-downloads-hourly": {
            "task": "periodic.cleanup_expired",
            "schedule": crontab(minute=15),  # every hour at :15
        },
    },
)