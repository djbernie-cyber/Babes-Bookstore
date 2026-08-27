import os
from celery import Celery
from .config import settings

celery_app = Celery(
    "babes_bookstore",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.scrape",
        "app.tasks.verify_licenses",
        "app.tasks.package_bundle",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,
    task_soft_time_limit=1500,
    worker_max_tasks_per_child=50,
    worker_concurrency=4,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)