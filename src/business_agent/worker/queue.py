from __future__ import annotations

from redis import Redis
from rq import Queue, Retry

from business_agent.worker.contracts import DocumentIngestionTask, SubagentTaskQueue


class RedisSubagentQueue(SubagentTaskQueue):
    def __init__(self, redis_url: str, queue_name: str) -> None:
        self._redis = Redis.from_url(redis_url)
        self._queue = Queue(name=queue_name, connection=self._redis)

    def enqueue_document_ingestion(self, task: DocumentIngestionTask) -> str:
        event_date = task.event_date.isoformat() if task.event_date else None
        job = self._queue.enqueue(
            "business_agent.worker.tasks.ingest_document_task",
            kwargs={
                "source_uri": task.source_uri,
                "event_date": event_date,
                "requester_id": task.requester_id,
            },
            job_timeout=900,
            result_ttl=86400,
            retry=Retry(max=2, interval=[10, 30]),
        )
        return job.id

