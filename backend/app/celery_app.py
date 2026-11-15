from celery import Celery

from app.core.config import settings

celery = Celery("contentos", broker=settings.redis_url, backend=settings.redis_url, include=["app.runs.tasks"])
celery.conf.update(task_track_started=True, task_acks_late=True, worker_prefetch_multiplier=1)
