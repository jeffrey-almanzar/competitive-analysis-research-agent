# Redis cache for fetched web pages, so re-running research on the same companies
# doesn't pay for (or wait on) the same Exa requests again.
#
# Cache hits skip the wrapped function entirely, so they are not counted as Exa requests.
# Set PAGE_CACHE_TTL_S=0 to disable. If Redis is unreachable, calls go straight through.

import hashlib
import json
import logging
import os
from dataclasses import asdict
from functools import lru_cache, wraps

import redis

log = logging.getLogger(__name__)

DEFAULT_TTL_S = 24 * 3600
KEY_PREFIX = "pagecache:v1"


def ttl_s() -> int:
    return int(os.getenv("PAGE_CACHE_TTL_S", DEFAULT_TTL_S))


@lru_cache(maxsize=1)
def _client() -> redis.Redis | None:
    url = os.getenv("REDIS_URL")
    if not url or ttl_s() <= 0:
        return None
    return redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)


def _key(namespace: str, args: tuple, kwargs: dict) -> str:
    payload = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    return f"{KEY_PREFIX}:{namespace}:{hashlib.sha256(payload.encode()).hexdigest()}"


def cached_pages(namespace: str, page_cls):
    """Cache a function returning a list of dataclass instances (e.g. search.Page)."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            client = _client()
            if client is None:
                return fn(*args, **kwargs)
            key = _key(namespace, args, kwargs)
            try:
                hit = client.get(key)
            except redis.RedisError as exc:
                log.warning("Page cache unavailable (%s); fetching directly", exc)
                return fn(*args, **kwargs)
            if hit is not None:
                log.info("Page cache hit: %s %s", namespace, args[:1])
                return [page_cls(**row) for row in json.loads(hit)]

            result = fn(*args, **kwargs)
            if result:  # don't cache empty results; they're often transient failures
                try:
                    client.set(key, json.dumps([asdict(p) for p in result]), ex=ttl_s())
                except redis.RedisError as exc:
                    log.warning("Could not write page cache: %s", exc)
            return result

        return wrapper

    return decorator
