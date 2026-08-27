"""Cache Redis com fallback em memória para o agent CLI."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PREFIX = "laravel_agent:"


class AgentCache:
  """Cache de consultas do agente (Redis ou dict local)."""

  def __init__(
    self,
    redis_url: str = "redis://127.0.0.1:6379/0",
    enabled: bool = True,
    default_ttl: int = 86400,
  ) -> None:
    self.enabled = enabled
    self.default_ttl = default_ttl
    self._memory: dict[str, tuple[Any, float]] = {}
    self._redis: Any = None
    self._backend = "memory"

    if not enabled:
      return

    try:
      import redis

      client = redis.Redis.from_url(redis_url, decode_responses=True)
      client.ping()
      self._redis = client
      self._backend = "redis"
      logger.info("Cache Redis conectado: %s", redis_url)
    except Exception as exc:
      logger.warning(
        "Redis indisponível (%s) — usando cache em memória.",
        exc,
      )
      self._backend = "memory"

  @property
  def backend(self) -> str:
    return self._backend

  def _key(self, namespace: str, raw: str) -> str:
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{_PREFIX}{namespace}:{digest}"

  def get(self, namespace: str, raw_key: str) -> Optional[Any]:
    if not self.enabled:
      return None

    key = self._key(namespace, raw_key)

    if self._redis is not None:
      try:
        payload = self._redis.get(key)
        if payload is None:
          return None
        return json.loads(payload)
      except Exception as exc:
        logger.debug("Redis get falhou: %s", exc)

    entry = self._memory.get(key)
    if entry is None:
      return None
    value, expires = entry
    if expires and time.time() > expires:
      del self._memory[key]
      return None
    return value

  def set(
    self,
    namespace: str,
    raw_key: str,
    value: Any,
    ttl: Optional[int] = None,
  ) -> None:
    if not self.enabled:
      return

    key = self._key(namespace, raw_key)
    ttl = ttl if ttl is not None else self.default_ttl
    payload = json.dumps(value, ensure_ascii=False)

    if self._redis is not None:
      try:
        self._redis.setex(key, ttl, payload)
        return
      except Exception as exc:
        logger.debug("Redis set falhou: %s", exc)

    expires = time.time() + ttl if ttl > 0 else 0
    self._memory[key] = (value, expires)

  def delete_namespace(self, namespace: str) -> int:
    """Remove entradas de um namespace (útil ao reindexar)."""
    prefix = f"{_PREFIX}{namespace}:"
    removed = 0

    if self._redis is not None:
      try:
        for key in self._redis.scan_iter(match=f"{prefix}*"):
          self._redis.delete(key)
          removed += 1
        return removed
      except Exception as exc:
        logger.debug("Redis delete_namespace falhou: %s", exc)

    for key in list(self._memory.keys()):
      if key.startswith(prefix):
        del self._memory[key]
        removed += 1
    return removed
