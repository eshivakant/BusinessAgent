from __future__ import annotations

from redis import Redis
from rq import Worker

from business_agent.config import get_settings


def main() -> None:
    settings = get_settings()
    redis_connection = Redis.from_url(settings.redis_url)
    worker = Worker([settings.rq_queue_name], connection=redis_connection)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
