from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "compintel",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "check-due-pages": {
            "task": "app.tasks.capture_tasks.check_due_pages",
            "schedule": crontab(minute=0, hour="*/1"),  # every hour
        },
        "send-weekly-digests": {
            "task": "app.tasks.digest_tasks.send_all_weekly_digests",
            "schedule": crontab(minute=0, hour=9, day_of_week=1),  # Monday 9am UTC
        },
        "collect-blog-signals": {
            "task": "app.tasks.signal_tasks.run_blog_collector",
            "schedule": crontab(minute=0, hour="*/6"),  # every 6 hours
        },
        "collect-hiring-signals": {
            "task": "app.tasks.signal_tasks.run_hiring_collector",
            "schedule": crontab(minute=30, hour="*/12"),  # every 12 hours
        },
        "collect-funding-signals": {
            "task": "app.tasks.signal_tasks.run_funding_collector",
            "schedule": crontab(minute=0, hour="*/12"),  # every 12 hours
        },
        "collect-review-signals": {
            "task": "app.tasks.signal_tasks.run_review_collector",
            "schedule": crontab(minute=0, hour=3),  # daily at 3am UTC
        },
    },
    task_routes={
        "app.tasks.capture_tasks.*": {"queue": "capture"},
        "app.tasks.digest_tasks.*": {"queue": "default"},
        "app.tasks.pipeline_tasks.*": {"queue": "default"},
        "app.tasks.signal_tasks.*": {"queue": "default"},
    },
)

celery_app.autodiscover_tasks(["app.tasks"])
