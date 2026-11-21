from celery import Celery

from app.core.config import settings

celery = Celery("contentos", broker=settings.redis_url, backend=settings.redis_url, include=["app.runs.tasks", "app.publishing.tasks"])
celery.conf.update(task_track_started=True, task_acks_late=True, worker_prefetch_multiplier=1)
celery.conf.beat_schedule = {"scheduler-tick": {"task": "scheduler.tick", "schedule": 30.0}}
